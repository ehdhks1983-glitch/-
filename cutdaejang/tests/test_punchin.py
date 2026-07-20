"""v0.55 👊 펀치인 줌 — z식·직렬화·실렌더 확대 실측·통합."""

import subprocess

from cutdaejang.core.render_engine import render
from cutdaejang.core.render_engine.ffmpeg_composer import build_command, punch_zoom_expr
from cutdaejang.spec import (AudioClip, Background, Canvas, Punch, Style, Subtitle,
                             TimelineSpec)
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


def test_punch_zoom_expr_and_command(tmp_path):
    e = punch_zoom_expr([Punch(start_us=3_000_000, end_us=4_200_000),
                         Punch(start_us=6_000_000, end_us=6_900_000)], 30)
    assert "between(on,90,126)" in e and "between(on,180,207)" in e
    assert "min(zoom+0.012,1.1)" in e and "max(zoom-0.008,1.0)" in e

    from tests.test_spec import make_valid_spec
    spec = make_valid_spec()
    args = build_command(spec, "v.wav", "s.ass", "o.mp4", fonts_dir=str(tmp_path))
    assert "zoompan" not in " ".join(args).replace(  # 기본 배경 모션의 zoompan 제외 확인
        next((a for a in args if "zoompan" in str(a) and "between" in str(a)), ""), "")
    spec.punchins = [Punch(start_us=0, end_us=1_000_000)]
    args2 = build_command(spec, "v.wav", "s.ass", "o.mp4", fonts_dir=str(tmp_path))
    joined = ";".join(a for a in args2 if isinstance(a, str))
    assert "between(on,0,30)" in joined and "[punch]" in joined

    # 직렬화 왕복
    spec2 = TimelineSpec.from_json(spec.to_json())
    assert spec2.punchins == [Punch(start_us=0, end_us=1_000_000)]


@requires_ffmpeg
def test_punch_zoom_visible_in_render(tmp_path):
    """흰 바탕+중앙 남색 사각형 배경 — 펀치 구간 프레임에서 사각형이 커지는지 실측."""
    bg = tmp_path / "bg.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=white:s=270x480:d=0.1",
            "-vf", "drawbox=x=54:y=96:w=162:h=288:color=navy:t=fill",
            "-frames:v", "1", str(bg)])
    wav = tmp_path / "s.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono:d=3", str(wav)])
    spec = TimelineSpec(
        canvas=Canvas(w=270, h=480, fps=30), duration_us=3_000_000,
        background=Background(type="image", path=str(bg), motion="off"),
        style=Style(gradient_overlay=False),
        audio=[AudioClip(path=str(wav), start_us=0, end_us=3_000_000)],
        subtitles=[Subtitle(text="x", start_us=0, end_us=3_000_000)],
        punchins=[Punch(start_us=200_000, end_us=1_500_000)],
    )
    res = render(spec, tmp_path / "work", out_path=str(tmp_path / "o.mp4"))
    assert res.ok, res.errors

    def navy_count(t):
        raw = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-ss", str(t), "-i", str(tmp_path / "o.mp4"),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True).stdout
        return sum(1 for i in range(0, len(raw), 3)
                   if raw[i] < 90 and raw[i + 1] < 90 and raw[i + 2] > 90)

    zoomed, back = navy_count(0.9), navy_count(2.8)
    # 1.1배 확대 → 사각형 면적 약 1.21배 (여유 두고 1.12배 이상), 복귀 프레임은 원래대로
    assert zoomed > back * 1.12, (zoomed, back)


@requires_ffmpeg
def test_run_job_places_punchins(tmp_path):
    from cutdaejang import config
    from cutdaejang.core import orchestrator
    from cutdaejang.core.orchestrator import JobOptions
    from cutdaejang.core.script_generator import StubScript

    res = orchestrator.run_job(
        tmp_path / "jobs", StubScript().generate("펀치"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True))
    assert res.status == "ok", res.errors
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    assert spec.punchins and all(p.end_us > p.start_us for p in spec.punchins)

    off = config.deep_merge(config.load_settings(), {"bg": {"punch_in": False}})
    res2 = orchestrator.run_job(
        tmp_path / "jobs2", StubScript().generate("펀치 끔"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True), settings=off)
    spec2 = TimelineSpec.load(f"{res2.job_dir}/spec.json")
    assert spec2.punchins == []
