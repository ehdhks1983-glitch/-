"""v1.32 — 목록 57: 왜 오래 걸리는지 «다음부터는 찍지 않고 바로 알게».

회원님 24차:
> "지금 4K 만들 때 오래 걸린다고 문구가 나오는데 … 이번에가 오래 걸린 거야"

51번에서 나는 로그를 보고도 원인을 못 가리고 «4K 때문»이라고 **찍었다.**
회원님이 두 번이나 바로잡아 주셔야 했다. 진짜 문제는 4K가 아니라
**어느 단계에서 몇 분을 썼는지 아무 데도 안 남는다**는 것이었다.

이 판은 그걸 남긴다:
  ① 단계별 소요 시간 — 로그와 완료 화면에
  ② 만들기 **전에** 예상 시간 — 단, 이 PC에서 배운 뒤에만
  ③ 목소리 만들 때 서버가 안 답하면 12분까지 매달리던 구멍
"""

import re
import tempfile
import time
from pathlib import Path

import pytest

from cutdaejang import __version__, config
from cutdaejang.core import tts_engine as te
from cutdaejang.gui import webui

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
HTML = webui._apply_links(webui._HTML)


def test_version():
    assert __version__ == "1.40.0"


# ── ① 단계별 소요 시간 ─────────────────────────────────────────
@pytest.mark.parametrize("sec,want", [
    (0, "0초"), (45, "45초"), (60, "1분"), (220, "3분 40초"),
    (3600, "1시간"), (3910, "1시간 5분"),
])
def test_dur_ko(sec, want):
    assert webui.dur_ko(sec) == want


def test_stage_report_says_where_the_time_went():
    """🔴 51번에서 내가 «4K 때문»이라고 찍은 이유 — 이게 없었다."""
    j = "보고테스트"
    base = time.monotonic()
    webui._STAGE_MARKS[j] = [(s, base + t) for s, t in (
        ("cut", 0), ("tts", 12), ("render", 232), ("done", 1312))]
    rep = webui.stage_report(j)
    assert rep.startswith("⏱ ")
    assert "화면 준비 12초" in rep
    assert "목소리 만들기 3분 40초" in rep
    assert "영상 굽기 18분" in rep
    assert "합계 21분 52초" in rep


def test_waiting_for_me_is_not_counted_as_work():
    """검토 대기는 회원님이 자리를 비운 시간이다 — 합계에 넣으면 보고가 쓸모없어진다."""
    j = "검토포함"
    base = time.monotonic()
    webui._STAGE_MARKS[j] = [(s, base + t) for s, t in (
        ("cut", 0), ("review", 10), ("render", 3610), ("done", 3670))]
    rep = webui.stage_report(j)
    assert "검토" not in rep
    assert "합계 1분 10초" in rep, rep      # 3600초짜리 대기는 빠져야 한다


def test_stage_marks_are_recorded_without_touching_any_call_site():
    """부르는 쪽을 안 바꿔도 되게 _set_job 한 곳에서 잰다 — 빠뜨릴 자리가 없다."""
    j = "자동기록"
    webui._STAGE_MARKS.pop(j, None)
    webui._set_job(j, status="running", stage="cut")
    webui._set_job(j, stage="tts", frac=0.2)
    webui._set_job(j, stage="tts", frac=0.9)      # 같은 단계 안 진행률은 안 센다
    webui._set_job(j, stage="render")
    assert [s for s, _ in webui._STAGE_MARKS[j]] == ["cut", "tts", "render"]


def test_report_lands_on_the_job_and_the_screen():
    j = "완료보고"
    base = time.monotonic()
    webui._STAGE_MARKS[j] = [(s, base + t) for s, t in
                             (("tts", 0), ("render", 30), ("done", 200))]
    webui._set_job(j, status="ok", stage="done")
    assert "⏱" in (webui._get_job(j) or {}).get("stage_report", "")
    assert 'id="stageReport"' in HTML          # 완료 화면에 자리가 있다
    assert "job.stage_report" in HTML          # 그 자리에 채워 넣는다


def test_old_jobs_do_not_pile_up_forever():
    for i in range(80):
        webui._set_job(f"쌓기{i}", stage="cut")
    assert len(webui._STAGE_MARKS) <= 60, "작업 기록이 무한히 쌓이면 메모리를 먹는다"


# ── ② 예상 시간 — 배운 뒤에만 말한다 ───────────────────────────
def test_we_do_not_guess_before_we_have_measured():
    """🔴 내 컴퓨터에서 잰 숫자를 박아 두면 회원님 PC에서 틀린 시간을 알려 준다.

    그래서 기본값은 **비어 있다** — 배우기 전에는 아무 말도 안 한다.
    """
    assert config.DEFAULTS["ui"]["render_speed"] == {}
    body = HTML.split("function etaSeconds(")[1].split("\nfunction ")[0]
    assert "if(!per || !(videoSec > 0)) return 0;" in body


def test_the_estimate_uses_what_this_pc_learned():
    body = HTML.split("function etaSeconds(")[1].split("\nfunction ")[0]
    assert "render_speed" in body and "videoSec * per" in body
    # 화면 세 곳에서 부른다 (블로그 대본·화질, 사진 길이·화질)
    assert HTML.count("updateEta()") >= 3
    assert HTML.count("updatePhotoEta()") >= 3


def test_learning_uses_the_real_render_time(tmp_path, monkeypatch):
    """이 PC가 «영상 1초에 몇 초» 걸리는지 실제 작업에서 배운다."""
    saved: dict = {}
    monkeypatch.setattr(webui.config, "load_settings", lambda: {"ui": {}})
    monkeypatch.setattr(webui.config, "save_settings", lambda d: saved.update(d))
    monkeypatch.setattr(webui, "_get_job", lambda j: {"params": {"quality": "ultra"}})
    mp4 = tmp_path / "out.mp4"
    mp4.write_bytes(b"x")
    monkeypatch.setattr("cutdaejang.utils.ffmpeg.probe_duration_us",
                        lambda p: 120_000_000)          # 영상 120초
    j = "학습"
    base = time.monotonic()
    webui._STAGE_MARKS[j] = [(s, base + t) for s, t in
                             (("tts", 0), ("render", 10), ("done", 550))]
    webui._learn_render_speed(j, "ultra", str(mp4))     # 굽기 540초 / 영상 120초
    assert saved["ui"]["render_speed"]["ultra"] == pytest.approx(4.5, abs=0.05)


def test_learning_ignores_samples_too_small_to_mean_anything(tmp_path, monkeypatch):
    saved: dict = {}
    monkeypatch.setattr(webui.config, "save_settings", lambda d: saved.update(d))
    monkeypatch.setattr("cutdaejang.utils.ffmpeg.probe_duration_us", lambda p: 1_000_000)
    mp4 = tmp_path / "x.mp4"
    mp4.write_bytes(b"x")
    j = "너무짧음"
    base = time.monotonic()
    webui._STAGE_MARKS[j] = [("render", base), ("done", base + 1)]
    webui._learn_render_speed(j, "standard", str(mp4))
    assert not saved, "1초짜리 표본으로 배우면 엉뚱한 예상 시간이 나온다"


# ── ③ 목소리 만들 때 매달리던 구멍 ─────────────────────────────
def _hang_run(per_call: float, monkeypatch):
    """요청 하나가 per_call초씩 걸리며 실패하는 상황."""
    clock = [0.0]
    monkeypatch.setattr(te.time, "monotonic", lambda: clock[0])

    class Hanging:
        name = "gemini"
        calls = 0

        def synthesize(self, text, voice, out_path):
            Hanging.calls += 1
            clock[0] += per_call
            raise te.TTSError("인터넷 연결 문제로 요청하지 못했어요: timed out")

    st = config.deep_merge(config.DEFAULTS, {})
    eng = te.TTSEngine(Hanging(), Path(tempfile.mkdtemp()), settings=st,
                       sleep=lambda s: clock.__setitem__(0, clock[0] + s))
    with pytest.raises(te.TTSExhausted):
        eng.synth_sentence("한 문장입니다")
    return Hanging.calls, clock[0], st["tts"]["retry_wait_cap_s"]


def test_a_hanging_server_no_longer_eats_twelve_minutes(monkeypatch):
    """🔴 회원님 40분 작업이 «키가 말썽이던 그 시기»였다.

    상한(120초)은 **재시도 사이 잠자는 시간만** 셌다. 요청이 타임아웃(120초)까지
    매달리는 건 예산에 안 들어가, 문장 하나에 (5+1)×120초 = 12분이 들어가도
    상한에 안 걸렸다. 이제 문장에 쓴 벽시계 시간 전체를 센다.
    """
    calls, spent, cap = _hang_run(120.0, monkeypatch)
    assert calls == 1, f"{calls}번이나 다시 시도했다"
    assert spent <= cap + 1, f"{spent:.0f}초를 썼다 (상한 {cap}초)"
    assert spent < 720, "고치기 전 최악값(12분)보다는 확실히 짧아야 한다"


def test_a_merely_slow_server_still_gets_its_retries(monkeypatch):
    """느리지만 답은 하는 서버에서는 재시도를 뺏으면 안 된다."""
    calls, spent, cap = _hang_run(30.0, monkeypatch)
    assert calls >= 3, f"재시도를 너무 일찍 포기했다 ({calls}번)"
    assert spent <= cap + 40


def test_the_budget_counts_wall_clock_not_just_sleep():
    src = (ROOT / "cutdaejang/core/tts_engine.py").read_text(encoding="utf-8")
    body = src.split("def _synth_raw_with_retry(")[1].split("\n    def ")[0]
    assert "t_started = time.monotonic()" in body
    assert "time.monotonic() - t_started + delay > wait_cap" in body
    assert "time.monotonic() - t_started >= wait_cap" in body


def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
