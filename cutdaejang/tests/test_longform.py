"""v0.61 — 롱폼(가로 16:9)·내 대본·영상 길이 (AI 영상 만들기 확장)."""
from cutdaejang.core import orchestrator
from cutdaejang.core.orchestrator import JobOptions
from cutdaejang.core.script_generator import Script, StubScript
from cutdaejang.spec import TimelineSpec
from cutdaejang.utils import ffmpeg as ff


def test_run_job_wide_renders_landscape(tmp_path):
    res = orchestrator.run_job(
        tmp_path / "jobs", StubScript().generate("가로 롱폼"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True, orientation="wide"))
    assert res.status == "ok", res.errors
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    assert (spec.canvas.w, spec.canvas.h) == (1920, 1080)
    w, h = ff.probe_video_size(res.mp4.out_path)
    assert (w, h) == (1920, 1080)


def test_run_job_default_stays_shorts(tmp_path):
    res = orchestrator.run_job(
        tmp_path / "jobs", StubScript().generate("세로 기본"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True))
    assert res.status == "ok", res.errors
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    assert (spec.canvas.w, spec.canvas.h) == (1080, 1920)


def test_user_script_markup_not_spoken(tmp_path):
    """[노랑]마크업[/]은 자막 전용 — TTS 입력에서 벗겨져야 한다 (stub 캐시 키로 확인)."""
    script = Script(title="마크업", sentences=["[노랑]첫[/] 문장", "둘째 문장"])
    res = orchestrator.run_job(
        tmp_path / "jobs", script,
        opts=JobOptions(tts_chain=["stub"], auto_mode=True))
    assert res.status == "ok", res.errors
    # 같은 문장을 마크업 없이 합성한 것과 캐시가 같아야 함 = 마크업이 제거돼 발음됨
    from cutdaejang.core import tts_engine
    eng = tts_engine.TTSEngine(tts_engine.StubTTS(), tmp_path / "jobs" / "cache" / "tts")
    p = eng.synth_sentence("첫 문장")
    assert p.exists()
    assert eng.stats["cache_hits"] >= 1, "마크업 제거 후 캐시가 재사용되어야 함"


def test_job_options_orientation_and_target_from_params():
    from cutdaejang.gui.webui import _job_options

    o = _job_options({"orientation": "wide", "target_sec": 180})
    assert o.orientation == "wide" and o.target_sec == 180
    o2 = _job_options({})
    assert o2.orientation == "shorts" and o2.target_sec == 60
    o3 = _job_options({"orientation": "이상한값"})
    assert o3.orientation == "shorts"
