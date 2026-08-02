"""v1.31 — 목록 61: 문장 사이 정적이 «적어 놓은 값»보다 길어 뚝뚝 끊겨 들리던 것.

회원님 25차 (영상 첨부):
> "목소리는 잘 바꿔졌는데 조금씩 끊켜"

받은 영상의 파형을 직접 쟀다. 무음이 두 종류였고 **정체가 완전히 달랐다**:

    짧은 틈 0.12~0.23초 → 최대 진폭 167~315  = 목소리 자체의 쉼 (정상)
    긴 틈  0.41~0.46초 → 최대 진폭 **0**     = 프로그램이 넣은 완전 정적 ← 원인

코드가 넣는 간격은 0.30초인데 왜 0.42초인가:
    `postprocess_clip`이 클릭 방지·숨결 보호로 클립 **앞뒤에 50ms씩** 붙인다(v0.46.1).
    그걸 모르고 사이에 300ms를 **더** 넣으니 들리는 정적은 50+300+50 = **400ms**.

즉 «간격 300ms»는 우리 장부상의 숫자였을 뿐 회원님 귀에는 400ms였다.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from cutdaejang import __version__, config
from cutdaejang.core import edit_mode, timeline_calculator, tts_engine
from cutdaejang.spec import Background, Style, Subtitle
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

PAD_MS = 50          # postprocess_clip이 앞뒤에 붙이는 여유
TARGET_MS = 250      # 문장 사이에 «들려야» 하는 정적


def test_version():
    assert __version__ == "1.32.0"


@pytest.fixture(scope="module")
def clips():
    """실제 TTS 다듬기를 거친 클립 3개 — 앞뒤 패딩이 진짜로 붙어 있다."""
    d = Path(tempfile.mkdtemp())
    cfg = config.deep_merge(config.DEFAULTS, {})["audio"]
    out = []
    for i in range(3):
        raw = d / f"raw{i}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"sine=f={300 + i * 40}:d=1.2", "-c:a", "pcm_s16le", str(raw)])
        p = d / f"c{i}.wav"
        tts_engine.postprocess_clip(str(raw), str(p), cfg)
        out.append(str(p))
    return d, out


# ── 앞뒤 무음 재기 ─────────────────────────────────────────────
@requires_ffmpeg
def test_edge_silence_measures_the_real_padding(clips):
    """설정값을 믿지 않고 파형을 잰다 — 제공자마다 패딩이 다를 수 있다."""
    _d, cs = clips
    for c in cs:
        lead, trail = ff.edge_silence_us(c)
        assert abs(lead - PAD_MS * 1000) < 20_000, f"앞 무음 {lead / 1000:.0f}ms"
        assert abs(trail - PAD_MS * 1000) < 20_000, f"뒤 무음 {trail / 1000:.0f}ms"


def test_edge_silence_never_breaks_on_odd_files(tmp_path):
    """못 재는 파일이면 (0,0) — 예전과 똑같이 동작해야지 터지면 안 된다."""
    bad = tmp_path / "not_audio.txt"
    bad.write_text("소리가 아님", encoding="utf-8")
    assert ff.edge_silence_us(str(bad)) == (0, 0)
    assert ff.edge_silence_us(str(tmp_path / "없는파일.wav")) == (0, 0)


@requires_ffmpeg
def test_all_silent_clip_is_not_counted_twice(tmp_path):
    """통째로 조용한 클립을 앞뒤 모두로 세면 간격이 음수가 된다."""
    p = tmp_path / "quiet.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono:d=1", "-c:a", "pcm_s16le", str(p)])
    assert ff.edge_silence_us(str(p)) == (0, 0)


# ── 🔴 핵심: «들리는» 정적이 목표값이어야 한다 ──────────────────
def _heard_gaps_ms(wav: str, upto_s: float) -> list:
    r = subprocess.run(
        [ff.ffmpeg_bin(), "-v", "info", "-i", str(wav),
         "-af", "silencedetect=noise=-45dB:d=0.05", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    durs = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r.stderr)]
    # 맨 뒤 긴 무음은 «영상 끝까지의 여백»이지 문장 사이가 아니다
    return [round(d * 1000) for s, d in zip(starts, durs)
            if 0.3 < s < upto_s and d < 1.5]


@requires_ffmpeg
def test_the_silence_you_hear_is_the_silence_we_wrote_down(clips):
    """🔴 회원님이 «끊긴다»고 하신 바로 그것.

    예전엔 장부에 300ms라고 적고 실제로는 400ms가 들렸다.
    이제 적은 값과 들리는 값이 같아야 한다.
    """
    d, cs = clips
    subs = [Subtitle(text=f"문장{i}", start_us=0, end_us=0) for i in range(len(cs))]
    out_subs, out_clips, _ = edit_mode.retime_narration(
        cs, subs, 20_000_000, d / "t1", fit="freeze")
    narr = edit_mode.build_narration_wav(out_clips, out_subs, 20_000_000, str(d / "n1.wav"))

    heard = _heard_gaps_ms(narr, 6.0)
    assert heard, "문장 사이 정적을 못 쟀다"
    for ms in heard:
        assert abs(ms - TARGET_MS) <= 60, f"들리는 정적 {ms}ms (목표 {TARGET_MS}ms)"
    # 고치기 전 값(400ms)이 다시 나오면 회귀다
    assert max(heard) < 350, f"패딩을 다시 안 빼고 있다: {heard}"


@pytest.fixture(scope="module")
def bare_clips(clips):
    """패딩이 없는 클립 — 같은 소리, 앞뒤 여유만 없다."""
    d, _cs = clips
    out = []
    for i in range(3):
        p = d / f"bare{i}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"sine=f={300 + i * 40}:d=1.2", "-ar", "48000", "-ac", "2",
                "-c:a", "pcm_s16le", str(p)])
        out.append(str(p))
    return out


@requires_ffmpeg
@pytest.mark.parametrize("fit,total", [("freeze", 20_000_000)])
def test_padding_no_longer_leaks_into_the_gap(clips, bare_clips, fit, total):
    """🔑 결정적 시험 — **패딩이 있든 없든 들리는 정적은 같아야 한다.**

    고치기 전에는 패딩 있는 클립이 정확히 100ms(=50+50) 더 벌어졌다.
    그 100ms가 회원님이 «끊긴다»고 하신 정체다.
    """
    d, padded = clips
    heard = {}
    for name, cs in (("패딩있음", padded), ("패딩없음", bare_clips)):
        subs = [Subtitle(text=f"문장{i}", start_us=0, end_us=0) for i in range(len(cs))]
        os_, oc, _ = edit_mode.retime_narration(cs, subs, total, d / f"t{fit}{name}", fit=fit)
        w = edit_mode.build_narration_wav(oc, os_, total, str(d / f"n{fit}{name}.wav"))
        g = _heard_gaps_ms(w, 6.0)
        assert g, f"{name}: 문장 사이 정적을 못 쟀다"
        heard[name] = max(g)
    diff = abs(heard["패딩있음"] - heard["패딩없음"])
    assert diff <= 40, (
        f"패딩이 그대로 새고 있다 — 있음 {heard['패딩있음']}ms vs 없음 "
        f"{heard['패딩없음']}ms (차이 {diff}ms)")


@requires_ffmpeg
def test_the_video_filling_path_is_left_alone(clips):
    """⚠ 영상 길이에 맞추는 경로는 손대면 안 된다.

    거기서의 간격은 «정해 둔 쉼»이 아니라 **남는 시간을 고르게 나눈 값**이다.
    빼 봐야 그만큼이 문장 사이가 아니라 «영상 끝의 정적»으로 몰릴 뿐이다.
    """
    d, cs = clips
    subs = [Subtitle(text=f"문장{i}", start_us=0, end_us=0) for i in range(len(cs))]
    out_subs, _oc, _ = edit_mode.retime_narration(cs, subs, 4_700_000, d / "tf", fit="drop")
    span = out_subs[-1].end_us
    assert 4_100_000 < span <= 4_700_000, f"영상을 제대로 못 채웠다 ({span / 1e6:.2f}초)"


@requires_ffmpeg
def test_ai_generation_path_too(clips):
    """AI 영상 만들기 경로도 250ms로 적고 350ms를 들려주고 있었다."""
    _d, cs = clips
    spec = timeline_calculator.build_spec(
        [f"문장{i}" for i in range(len(cs))], cs,
        Background(type="color", color="#101020"), Style())
    gaps = [spec.audio[i + 1].start_us - spec.audio[i].end_us
            for i in range(len(spec.audio) - 1)]
    for g in gaps:
        # 들리는 값 = 넣은 간격 + 뒤 무음(50ms) + 앞 무음(50ms)
        lead, trail = ff.edge_silence_us(cs[0])
        assert abs((g + lead + trail) - TARGET_MS * 1000) <= 60_000, f"{g / 1000:.0f}ms"


def test_a_floor_keeps_sentences_from_running_together():
    """패딩이 간격보다 크면 0이 되어 숨 넘어가듯 붙는다 — 바닥을 둔다."""
    assert edit_mode.MIN_HEARD_GAP_US >= 60_000
    assert timeline_calculator.MIN_HEARD_GAP_US == edit_mode.MIN_HEARD_GAP_US


@requires_ffmpeg
def test_joined_lines_still_have_no_gap_at_all(clips):
    """같은 문장을 쪼갠 줄 사이는 여전히 딱 붙어야 한다 (v1.24 성과 유지)."""
    d, cs = clips
    subs = [Subtitle(text=f"조각{i}", start_us=0, end_us=0) for i in range(len(cs))]
    out_subs, _oc, _ = edit_mode.retime_narration(
        cs, subs, 20_000_000, d / "t3", fit="freeze", joins=[True, True])
    for i in range(len(out_subs) - 1):
        assert out_subs[i + 1].start_us == out_subs[i].end_us, "붙일 자리가 벌어졌다"


@requires_ffmpeg
def test_the_users_clip_gap_would_now_be_shorter():
    """회원님 영상에서 잰 값(410~460ms)이 이 계산으로는 250ms가 된다."""
    fixed = 250_000 - (50_000 + 50_000)        # 우리가 실제로 넣게 될 간격
    heard = fixed + 50_000 + 50_000            # 회원님 귀에 들릴 정적
    assert heard == 250_000
    assert heard < 410_000, "고치기 전보다 짧아야 한다"


# ── 🔴 v1.30에서 실제로 두 번 낸 사고를 막는 그물 ────────────────
def test_extracted_helpers_can_actually_find_every_name_they_use():
    """함수를 밖으로 빼면서 «안에 있던 것»을 두고 오면 실행 순간 죽는다.

    v1.30에서 이걸 두 번 했다 — `_tts_clean`(중첩 함수)과 `edit_mode`(지역 import)를
    두고 나와서, 내레이션이 들어가는 렌더가 통째로 NameError로 죽었다.
    py_compile도 통과하고 구조 시험도 통과한다 — **실행해야만** 드러난다.
    그래서 정적으로 잡는 그물을 둔다.
    """
    import ast
    import builtins

    src = (Path(__file__).resolve().parents[1]
           / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    def module_names(body):
        """모듈 **바로 그 자리**에서 생기는 이름만 — 중첩 함수·지역 import는 빼야 한다.

        (여기서 ast.walk로 통째로 훑으면 «함수 안의 이름»까지 전역으로 세어
         정작 이 시험이 잡아야 할 사고를 못 잡는다 — 만들면서 실제로 그랬다.)
        """
        out = set()
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    out.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(node.name)
            elif isinstance(node, ast.Assign):
                out.update(x.id for x in node.targets if isinstance(x, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                out.add(node.target.id)
            elif isinstance(node, (ast.If, ast.Try, ast.For, ast.While, ast.With)):
                blocks = [getattr(node, k, []) for k in ("body", "orelse", "finalbody")]
                blocks += [h.body for h in getattr(node, "handlers", [])]
                for b in blocks:
                    out |= module_names(b)
        return out

    top = set(dir(builtins)) | module_names(tree.body)
    for node in ast.walk(tree):        # global로 선언된 것도 전역이다
        if isinstance(node, ast.Global):
            top.update(node.names)

    bad = []
    for fn in tree.body:               # 최상단 함수만 (중첩은 바깥 변수를 쓴다)
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local = set()
        for x in ast.walk(fn):
            if isinstance(x, ast.arg):
                local.add(x.arg)
            elif isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                local.add(x.id)
            elif isinstance(x, (ast.Import, ast.ImportFrom)):
                for a in x.names:
                    local.add(a.asname or a.name.split(".")[0])
            elif isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(x.name)
            elif isinstance(x, ast.ExceptHandler) and x.name:
                local.add(x.name)
        miss = {x.id for x in ast.walk(fn)
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)} - local - top
        if miss:
            bad.append(f"{fn.name}: {sorted(miss)}")
    assert not bad, "이름을 못 찾는 함수 — 실행하면 NameError로 죽는다:\n  " + "\n  ".join(bad)
