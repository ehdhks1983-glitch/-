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
