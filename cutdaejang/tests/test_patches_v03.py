"""작업지시서 v0.3 패치 검증 — 429 안정화·트림·BGM·줌·자막 강조."""

import json
from pathlib import Path

import pytest

from cutdaejang import config
from cutdaejang.core import orchestrator, tts_engine
from cutdaejang.core.render_engine.ass_writer import dialogue_text
from cutdaejang.core.render_engine.ffmpeg_composer import build_command
from cutdaejang.core.script_generator import Script
from cutdaejang.core.tts_engine import (
    RateLimiter,
    StubTTS,
    TTSEngine,
    TTSHTTPError,
    TTSNonRetryable,
    parse_retry_delay_s,
    synth_with_fallback,
)
from cutdaejang.spec import Bgm, Style, Subtitle
from tests.conftest import requires_ffmpeg
from tests.test_spec import make_valid_spec

RETRY_PAYLOAD = {
    "error": {
        "code": 429,
        "message": "Quota exceeded ... Please retry in 18.210819764s.",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "18.210819764s"}
        ],
    }
}


# ─────────── PATCH 1-1: retryDelay 파싱 ───────────


def test_parse_retry_delay_from_retryinfo():
    err = TTSHTTPError(429, RETRY_PAYLOAD, json.dumps(RETRY_PAYLOAD))
    assert parse_retry_delay_s(err) == pytest.approx(18.210819764)


def test_parse_retry_delay_regex_fallback():
    err = TTSHTTPError(429, None, '..."message": "Please retry in 25.995628153s."...')
    assert parse_retry_delay_s(err) == pytest.approx(25.995628153)


def test_parse_retry_delay_absent():
    assert parse_retry_delay_s(TTSHTTPError(429, None, "no hint here")) is None


# ─────────── PATCH 1-2: 레이트리미터 ───────────


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_rate_limiter_paces_after_window_full():
    clk = FakeClock()
    rl = RateLimiter(rpm=8, clock=clk.now, sleep=clk.sleep)
    for _ in range(8):
        assert rl.acquire() == 0.0  # 한도 내 즉시 통과
    waited = rl.acquire()  # 9번째 → 윈도우 해제까지 대기
    assert 59.0 <= waited <= 61.5
    assert sum(clk.slept) == pytest.approx(waited)


# ─────────── PATCH 1-1/1-4: 재시도·폴백 ───────────


class Flaky429Provider:
    """N번 429를 던진 뒤 성공하는 가짜 제공자."""

    name = "gemini"
    model = "fake-tts"

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def synthesize(self, text, voice, out_path):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TTSHTTPError(429, RETRY_PAYLOAD, json.dumps(RETRY_PAYLOAD))
        StubTTS().synthesize(text, voice, out_path)
        return out_path


@requires_ffmpeg
def test_retry_waits_server_delay_then_succeeds(tmp_path):
    clk = FakeClock()
    provider = Flaky429Provider(fail_times=2)
    engine = TTSEngine(provider, tmp_path / "cache", sleep=clk.sleep,
                       limiter=RateLimiter(8, clock=clk.now, sleep=clk.sleep))
    path = engine.synth_sentence("재시도 테스트 문장입니다")
    assert path.exists()
    assert provider.calls == 3
    # 2회 재시도 각각 retryDelay(18.2s)+지터(1~2s) 대기
    assert 2 * 19.2 <= sum(clk.slept) <= 2 * 20.3


def test_auth_error_is_non_retryable(tmp_path):
    class Auth401Provider:
        name = "gemini"
        model = "fake"

        def synthesize(self, text, voice, out_path):
            raise TTSHTTPError(401, None, "unauthorized")

    clk = FakeClock()
    engine = TTSEngine(Auth401Provider(), tmp_path / "c", sleep=clk.sleep,
                       limiter=RateLimiter(8, clock=clk.now, sleep=clk.sleep))
    with pytest.raises(TTSNonRetryable):
        engine.synth_sentence("인증 오류 문장")
    assert clk.slept == []  # 대기 없이 즉시 실패


@requires_ffmpeg
def test_wait_cap_exhausts(tmp_path):
    clk = FakeClock()
    settings = config.deep_merge(config.load_settings(), {"tts": {"retry_wait_cap_s": 10}})
    engine = TTSEngine(Flaky429Provider(fail_times=99), tmp_path / "c", settings=settings,
                       sleep=clk.sleep, limiter=RateLimiter(8, clock=clk.now, sleep=clk.sleep))
    with pytest.raises(tts_engine.TTSExhausted, match="대기 상한"):
        engine.synth_sentence("상한 테스트")


@requires_ffmpeg
def test_fallback_chain_falls_to_stub(tmp_path):
    class AlwaysAuthFail:
        name = "gemini"
        model = "fake"

        def synthesize(self, text, voice, out_path):
            raise TTSHTTPError(403, None, "forbidden")

    notes = []
    paths, used, reason = synth_with_fallback(
        ["폴백 체인 테스트 문장"],
        chain=["gemini"],
        cache_root=tmp_path / "cache",
        status_cb=notes.append,
        providers={"gemini": AlwaysAuthFail()},
    )
    assert used == "stub"
    assert len(paths) == 1 and paths[0].exists()
    assert reason and "폴백" in reason


# ─────────── PATCH 1-3: 영구 캐시 (동일 대본 재실행 시 API 0회) ───────────


@requires_ffmpeg
def test_cache_hit_on_rerun(tmp_path):
    sentences = ["캐시 첫 문장.", "캐시 둘째 문장."]
    e1 = TTSEngine(StubTTS(), tmp_path / "cache")
    e1.synth_all(sentences)
    assert e1.stats["api_calls"] == 2 and e1.stats["cache_hits"] == 0

    e2 = TTSEngine(StubTTS(), tmp_path / "cache")  # 새 실행 (엔진 재생성)
    e2.synth_all(sentences)
    assert e2.stats["api_calls"] == 0 and e2.stats["cache_hits"] == 2


@requires_ffmpeg
def test_cache_key_includes_style(tmp_path):
    e = TTSEngine(StubTTS(), tmp_path / "cache")
    other = config.deep_merge(config.load_settings(), {"tts": {"style_preset": "텐션형"}})
    e_style = TTSEngine(StubTTS(), tmp_path / "cache", settings=other)
    assert e.cache_path("같은 문장", "") != e_style.cache_path("같은 문장", "")


# ─────────── PATCH 2: 무음 트림 ───────────


@requires_ffmpeg
def test_postprocess_trims_padding_silence(tmp_path):
    from cutdaejang.utils import ffmpeg as ff

    raw = tmp_path / "raw.wav"
    # 0.5s 무음 + 1s 톤 + 0.5s 무음 = 2s
    ff.run(
        [
            ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-af", "adelay=500:all=1,apad=pad_dur=0.5",
            "-c:a", "pcm_s16le", "-f", "wav", str(raw),
        ]
    )
    raw_us, out_us = tts_engine.postprocess_clip(
        str(raw), str(tmp_path / "out.wav"), config.load_settings()["audio"]
    )
    assert raw_us >= 1_900_000
    assert out_us <= 1_250_000          # 무음 제거됨 (1s 톤 + 60ms 패드 근방)
    assert raw_us - out_us >= 700_000   # 총 0.7초 이상 단축


# ─────────── PATCH 3/4: BGM·Ken Burns 명령 ───────────


def _cmd(spec, **kw):
    defaults = dict(voice_path="voice.m4a", ass_path="s.ass", out_path="o.mp4",
                    fonts_dir="/fonts")
    defaults.update(kw)
    return " ".join(map(str, build_command(spec, **defaults)))


def test_zoompan_used_when_motion_on():
    spec = make_valid_spec()
    spec.background.motion = "zoom_in"
    cmd = _cmd(spec)
    assert "zoompan=z='min(1+0.08*on/150,1+0.08)'" in cmd  # 5초*30fps=150프레임
    assert "scale=1620:2880" in cmd  # 1.5배 업스케일 (저사양 최적화)
    assert "-loop 1" not in cmd


def test_zoom_out_expression():
    spec = make_valid_spec()
    spec.background.motion = "zoom_out"
    assert "zoompan=z='max(1+0.08-0.08*on/150,1)'" in _cmd(spec)


def test_motion_off_keeps_legacy_chain():
    spec = make_valid_spec()
    spec.background.motion = "off"
    cmd = _cmd(spec)
    assert "-loop 1 -t 5.000000" in cmd and "zoompan" not in cmd


def test_bgm_mix_normalize_zero():
    spec = make_valid_spec()
    spec.bgm = Bgm(path="bgm.mp3", volume_db=-20)
    cmd = _cmd(spec)
    assert "-stream_loop -1 -i bgm.mp3" in cmd
    assert "volume=-20dB,atrim=0:5.000000,afade=t=in:d=0.5,afade=t=out:st=3.500:d=1.5" in cmd
    assert "amix=inputs=2:duration=first:normalize=0[aout]" in cmd
    assert "-map [v] -map [aout]" in cmd


def test_bgm_duck_uses_sidechain():
    spec = make_valid_spec()
    spec.bgm = Bgm(path="bgm.mp3", duck=True)
    cmd = _cmd(spec)
    assert "sidechaincompress" in cmd and "asplit" in cmd


def test_no_bgm_maps_voice_directly():
    spec = make_valid_spec()
    assert "-map [v] -map 1:a" in _cmd(spec)


# ─────────── PATCH 5: 자막 강조·페이드 ───────────


def test_dialogue_highlight_coloring():
    style = Style(fade=False, highlight_color="#FFD400")
    sub = Subtitle("오늘의 핵심은 습관입니다", 0, 1_000_000, highlight="습관")
    text = dialogue_text(sub, style)
    assert text == "오늘의 핵심은 {\\1c&H00D4FF&}습관{\\1c&HFFFFFF&}입니다"


def test_dialogue_fade_tag():
    style = Style(fade=True)
    sub = Subtitle("페이드 문장", 0, 1_000_000)
    assert dialogue_text(sub, style).startswith("{\\fad(100,60)}")


def test_dialogue_highlight_missing_word_ignored():
    style = Style(fade=False)
    sub = Subtitle("본문에 없는 단어", 0, 1_000_000, highlight="딴단어")
    assert dialogue_text(sub, style) == "본문에 없는 단어"


# ─────────── PATCH 5-1: 대본 highlight 스키마 ───────────


def test_script_parses_object_sentences_with_highlight():
    raw = json.dumps({
        "title": "t",
        "sentences": [
            {"text": "첫 문장", "highlight": "첫"},
            {"text": "둘째 문장", "highlight": ""},
        ],
    })
    s = Script.from_json_text(raw)
    assert s.sentences == ["첫 문장", "둘째 문장"]
    assert s.highlights == ["첫", ""]


def test_script_parses_legacy_string_sentences():
    s = Script.from_json_text('{"title":"t","sentences":["하나","둘"]}')
    assert s.sentences == ["하나", "둘"]
    assert s.highlights == ["", ""]


def test_script_json_roundtrip_keeps_highlights():
    s = Script(title="t", sentences=["가", "나"], highlights=["가", ""])
    restored = Script.from_json_text(s.to_json())
    assert restored.highlights == ["가", ""]


# ─────────── 설정·BGM 해석 ───────────


def test_settings_deep_merge():
    merged = config.deep_merge(config.DEFAULTS, {"tts": {"rpm_limit": 3}})
    assert merged["tts"]["rpm_limit"] == 3
    assert merged["tts"]["max_retries"] == config.DEFAULTS["tts"]["max_retries"]
    assert config.DEFAULTS["tts"]["rpm_limit"] == 8  # 원본 불변


def test_resolve_bgm(tmp_path):
    settings = config.load_settings()
    (tmp_path / "track.mp3").write_bytes(b"x")
    assert orchestrator.resolve_bgm("", settings, tmp_path) is None
    bgm = orchestrator.resolve_bgm("track.mp3", settings, tmp_path)
    assert bgm and bgm.path.endswith("track.mp3") and bgm.volume_db == -20
    assert orchestrator.resolve_bgm("random", settings, tmp_path).path.endswith("track.mp3")
    assert orchestrator.resolve_bgm("없는파일.mp3", settings, tmp_path) is None


# ─────────── 배경 이미지 실패가 작업을 죽이지 않아야 함 (사용자 404 리포트) ───────────


@requires_ffmpeg
def test_background_falls_back_on_any_provider_error(tmp_path):
    """404 등 어떤 예외가 나도 로컬 그라데이션으로 폴백해 배경 PNG를 만든다."""
    from cutdaejang.core import background_generator as bg
    from cutdaejang.spec import Canvas

    class Broken404Provider:
        def generate(self, prompt, out_path, canvas):
            # 사용자가 겪은 404를 그대로 재현 (TTSHTTPError 계열)
            from cutdaejang.core.tts_engine import TTSHTTPError

            raise TTSHTTPError(404, None, "model not found")

    out = tmp_path / "bg.png"
    notes = []
    result, source = bg.prepare_background(
        str(out), Canvas(), prompt="테스트", provider=Broken404Provider(),
        on_note=notes.append,
    )
    assert Path(result).exists()  # 폴백 배경이 실제로 생성됨
    assert notes and "기본 배경" in notes[0]
    assert source.startswith("ai_fail:")  # 완료 화면 표시용 출처 (v0.40)


def test_prepare_background_source_values(tmp_path):
    """v0.40: 배경 출처가 완료 화면에 그대로 보임 — local/ai 값 검증."""
    from cutdaejang.core import background_generator as bg
    from cutdaejang.core.background_generator import Canvas

    _, src = bg.prepare_background(str(tmp_path / "a.png"), Canvas(), prompt="x")
    assert src == "local"

    class OkProvider:
        def generate(self, prompt, out_path, canvas):
            Path(out_path).write_bytes(b"\x89PNG fake")
            return out_path

    _, src = bg.prepare_background(
        str(tmp_path / "b.png"), Canvas(), prompt="x", provider=OkProvider())
    assert src == "ai"


def test_ai_image_setup_gating(monkeypatch):
    """v0.40: AI 배경은 목소리와 무관 — 키만 있으면 적용(테스트 톤 제외), 사유 문구 확인."""
    from cutdaejang.gui import webui

    settings = {"bg": {"ai_image": True, "image_model": "m"}}
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    p, why = webui._ai_image_setup({"tts_provider": "windows"}, settings)
    assert p is None and "키 없음" in why

    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    p, why = webui._ai_image_setup({"tts_provider": "windows"}, settings)  # 내장 음성도 OK
    assert p is not None and why == ""
    p, why = webui._ai_image_setup({"tts_provider": "stub"}, settings)     # 테스트 톤만 제외
    assert p is None and "테스트 톤" in why
    p, why = webui._ai_image_setup({"tts_provider": "gemini"}, {"bg": {"ai_image": False}})
    assert p is None and "꺼짐" in why


def test_ai_image_off_by_default():
    assert config.DEFAULTS["bg"]["ai_image"] is False
    assert config.load_settings()["bg"]["image_model"]  # 모델명 설정 존재


# ─────────── v0.27: 내 목소리 클로닝 (ElevenLabs) ───────────


def test_elevenlabs_requires_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(tts_engine.TTSError):
        tts_engine.make_provider("elevenlabs", config.load_settings())


def test_elevenlabs_synthesize_needs_registered_voice(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    p = tts_engine.make_provider("elevenlabs", config.load_settings())
    with pytest.raises(TTSNonRetryable, match="등록"):
        p.synthesize("안녕하세요", "", str(tmp_path / "x.wav"))  # 클론 등록 전


def test_clone_voice_validates_inputs(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(tts_engine.TTSError, match="키"):
        tts_engine.clone_voice("내 목소리", str(tmp_path / "x.mp3"))
    with pytest.raises(tts_engine.TTSError, match="찾을 수 없"):
        tts_engine.clone_voice("내 목소리", str(tmp_path / "x.mp3"), api_key="k")


def test_clone_voice_builds_multipart_and_parses_id(tmp_path, monkeypatch):
    rec = tmp_path / "voice.mp3"
    rec.write_bytes(b"ID3fakemp3bytes")
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps({"voice_id": "abc123"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["data"] = req.data
        return FakeResp()

    monkeypatch.setattr(tts_engine.urllib.request, "urlopen", fake_urlopen)
    vid = tts_engine.clone_voice("내 목소리", str(rec), api_key="k123")
    assert vid == "abc123"
    assert "voices/add" in captured["url"]
    assert captured["headers"].get("Xi-api-key") == "k123"
    body = captured["data"]
    assert b'name="name"' in body and "내 목소리".encode() in body
    assert b'name="files"' in body and b"ID3fakemp3bytes" in body
    assert b"audio/mpeg" in body


def test_resolve_voice_elevenlabs_uses_saved_clone_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    settings = config.deep_merge(config.load_settings(), {"tts": {"voice_elevenlabs": "vid9"}})
    eng = TTSEngine(tts_engine.make_provider("elevenlabs", settings), tmp_path, settings=settings)
    assert eng._resolve_voice("") == "vid9"


# ─────────── v0.28: GPT-SoVITS 무료 로컬 내 목소리 ───────────


def test_sovits_requires_ref_audio():
    with pytest.raises(tts_engine.TTSError, match="참조 녹음"):
        tts_engine.make_provider("sovits", config.load_settings())


def test_sovits_connection_refused_is_nonretryable(tmp_path):
    p = tts_engine.GPTSoVITSTTS(url="http://127.0.0.1:1", ref_audio="ref.wav", ref_text="안녕")
    with pytest.raises(TTSNonRetryable, match="연결할 수 없"):
        p.synthesize("테스트 문장", "", str(tmp_path / "o.wav"))


def test_sovits_posts_korean_zero_shot_request(tmp_path):
    import http.server
    import threading

    got = {}
    fake_wav = b"RIFF" + b"\x00" * 2000  # 1KB 이상이면 통과

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got["path"] = self.path
            got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.end_headers()
            self.wfile.write(fake_wav)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = tts_engine.GPTSoVITSTTS(url=f"http://127.0.0.1:{srv.server_address[1]}",
                                    ref_audio="C:/rec/ref.wav", ref_text="안녕하세요 곰대리입니다")
        out = tmp_path / "o.wav"
        p.synthesize("오늘의 꿀팁을 소개합니다", "", str(out))
    finally:
        srv.shutdown()
    assert out.read_bytes() == fake_wav
    assert got["path"] == "/tts"
    b = got["body"]
    assert b["text"] == "오늘의 꿀팁을 소개합니다"
    assert b["text_lang"] == "ko" and b["prompt_lang"] == "ko"
    assert b["ref_audio_path"] == "C:/rec/ref.wav"
    assert b["prompt_text"] == "안녕하세요 곰대리입니다"
    assert b["media_type"] == "wav"


def test_sovits_empty_response_is_nonretryable(tmp_path):
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x")  # 1KB 미만 = 비정상

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = tts_engine.GPTSoVITSTTS(url=f"http://127.0.0.1:{srv.server_address[1]}",
                                    ref_audio="r.wav", ref_text="안녕")
        with pytest.raises(TTSNonRetryable, match="비어"):
            p.synthesize("문장", "", str(tmp_path / "o.wav"))
    finally:
        srv.shutdown()


def test_sovits_cache_key_changes_with_reference(tmp_path, monkeypatch):
    # 참조 녹음을 바꾸면 다른 목소리 → 캐시 키도 달라져야 한다 (v0.33.1)
    settings = config.load_settings()
    e1 = TTSEngine(tts_engine.GPTSoVITSTTS(ref_audio="a.wav", ref_text="안녕"), tmp_path,
                   settings=settings)
    e2 = TTSEngine(tts_engine.GPTSoVITSTTS(ref_audio="b.wav", ref_text="안녕"), tmp_path,
                   settings=settings)
    e3 = TTSEngine(tts_engine.GPTSoVITSTTS(ref_audio="a.wav", ref_text="안녕"), tmp_path,
                   settings=settings)
    k1, k2, k3 = (e.cache_path("같은 문장", "") for e in (e1, e2, e3))
    assert k1 != k2          # 참조 다름 → 키 다름
    assert k1 == k3          # 참조 같음 → 키 재사용
    # 기존 제공자(cache_extra 없음)는 키 형식이 그대로라 기존 캐시 유지
    g = TTSEngine(StubTTS(), tmp_path, settings=settings)
    assert g.cache_path("같은 문장", "") == g.cache_path("같은 문장", "")


def test_windows_tts_rate_setting():
    """v0.44 내장 음성 속도 — 설정 → 제공자 rate·캐시 키 반영, 스크립트 치환 가능."""
    from cutdaejang.core import tts_engine as te

    p = te.make_provider("windows", {"tts": {"windows_rate": 2}})
    assert p.rate == 2 and p.cache_extra == "rate2"
    # 기본(0)은 캐시 키 추가 없음 → 기존 캐시 그대로 재사용
    p0 = te.make_provider("windows", {"tts": {}})
    assert p0.rate == 0 and p0.cache_extra == ""
    # 범위 밖 값은 안전하게 클램프
    assert te.WindowsTTS(rate=99).rate == 10
    assert te.WindowsTTS(rate="이상한값").rate == 0
    # PS1 템플릿에 치환 지점이 있고, 치환하면 사라짐
    assert "__RATE__" in te._SAPI_PS1
    assert "__RATE__" not in te._SAPI_PS1.replace("__RATE__", "2")
