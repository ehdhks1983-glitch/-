"""v0.56 🎨 화면 톤 + 🔢 숫자 인포 팝 — 필터·이벤트·실렌더 실측·통합."""

import subprocess
from pathlib import Path

from cutdaejang.core.render_engine import render
from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.core.render_engine.ffmpeg_composer import TONE_PRESETS, build_command
from cutdaejang.spec import (AudioClip, Background, Canvas, InfoPop, Style, Subtitle,
                             TimelineSpec)
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


def test_tone_filter_in_command(tmp_path):
    from tests.test_spec import make_valid_spec

    assert set(TONE_PRESETS) == {"기본", "시네마틱", "화사", "선명", "흑백"}
    spec = make_valid_spec()
    args = " ".join(str(a) for a in build_command(
        spec, "v.wav", "s.ass", "o.mp4", fonts_dir=str(tmp_path)))
    assert "hue=s=0" not in args                       # 기본 톤 = 필터 없음
    spec.style.tone = "흑백"
    args2 = " ".join(str(a) for a in build_command(
        spec, "v.wav", "s.ass", "o.mp4", fonts_dir=str(tmp_path)))
    assert "hue=s=0" in args2 and "[tone]" in args2


def test_infopop_ass_events(tmp_path):
    spec = TimelineSpec(
        canvas=Canvas(w=1080, h=1920), duration_us=3_000_000,
        subtitles=[Subtitle(text="x", start_us=0, end_us=1_000_000)],
        infopops=[InfoPop(text="3가지", start_us=100_000, end_us=1_000_000)])
    txt = Path(write_ass(spec, tmp_path / "i.ass")).read_text(encoding="utf-8")
    assert "Style: Info" in txt
    ev = next(ln for ln in txt.splitlines() if ",Info," in ln)
    assert "3가지" in ev and "\\an5" in ev and "\\t(0,140" in ev and "\\fad(60,200)" in ev
    # 직렬화 왕복
    spec2 = TimelineSpec.from_json(spec.to_json())
    assert spec2.infopops == spec.infopops


@requires_ffmpeg
def test_tone_and_infopop_visible_in_render(tmp_path):
    """빨간 배경 + 흑백 톤 → 채도 소멸 실측 / 인포 팝 구간에 밝은 글자 픽셀."""
    bg = tmp_path / "bg.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=red:s=270x480:d=0.1", "-frames:v", "1", str(bg)])
    wav = tmp_path / "s.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono:d=3", str(wav)])

    def render_spec(tone, infopops, name):
        spec = TimelineSpec(
            canvas=Canvas(w=270, h=480, fps=30), duration_us=3_000_000,
            background=Background(type="image", path=str(bg), motion="off"),
            style=Style(gradient_overlay=False, tone=tone),
            audio=[AudioClip(path=str(wav), start_us=0, end_us=3_000_000)],
            subtitles=[Subtitle(text="x", start_us=2_500_000, end_us=3_000_000)],
            infopops=infopops)
        res = render(spec, tmp_path / f"w_{name}", out_path=str(tmp_path / f"{name}.mp4"))
        assert res.ok, res.errors
        return str(tmp_path / f"{name}.mp4")

    def frame(mp4, t):
        return subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-ss", str(t), "-i", mp4, "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True).stdout

    mono = render_spec("흑백", [], "mono")
    raw = frame(mono, 1.0)
    # 흑백: R≈G≈B (채도 소멸) — 픽셀 90% 이상에서 채널 차이가 작아야
    close = sum(1 for i in range(0, len(raw), 3)
                if abs(raw[i] - raw[i + 1]) < 14 and abs(raw[i + 1] - raw[i + 2]) < 14)
    assert close / (len(raw) / 3) > 0.9

    pop = render_spec("기본", [InfoPop(text="3가지", start_us=300_000,
                                      end_us=1_500_000)], "pop")
    def bright_mid(t):
        raw2 = frame(pop, t)
        w = 270
        cnt = 0
        for y in range(140, 250):          # 중상단(0.40h 부근) 밴드
            for x in range(0, w):
                i = (y * w + x) * 3
                if raw2[i] > 190 and raw2[i + 1] > 150:
                    cnt += 1
        return cnt
    assert bright_mid(0.9) > 300           # 팝 구간 — 노란 큰 숫자
    assert bright_mid(2.4) < 40            # 팝 종료 후엔 없음


@requires_ffmpeg
def test_run_job_places_infopops(tmp_path):
    from cutdaejang import config
    from cutdaejang.core import orchestrator
    from cutdaejang.core.orchestrator import JobOptions
    from cutdaejang.core.script_generator import Script

    script = Script(title="숫자 테스트", sentences=[
        "첫 문장은 그냥 갑니다", "핵심은 3가지 방법입니다", "하루 10분이면 충분해요"],
        highlights=["", "3가지", "10분"])
    res = orchestrator.run_job(tmp_path / "jobs", script,
                               opts=JobOptions(tts_chain=["stub"], auto_mode=True))
    assert res.status == "ok", res.errors
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    texts = [p.text for p in spec.infopops]
    assert any("3가지" in t for t in texts) and any("10분" in t for t in texts)

    off = config.deep_merge(config.load_settings(), {"subtitle": {"info_pop": False}})
    res2 = orchestrator.run_job(tmp_path / "jobs2", script,
                                opts=JobOptions(tts_chain=["stub"], auto_mode=True),
                                settings=off)
    assert TimelineSpec.load(f"{res2.job_dir}/spec.json").infopops == []
