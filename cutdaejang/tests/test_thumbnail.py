"""유튜브 썸네일(16:9) 생성 테스트."""

import pytest

from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


def test_suggest_thumbnail_stub():
    from cutdaejang.core.script_generator import suggest_thumbnail_copy_stub

    copies = suggest_thumbnail_copy_stub("블로그 자동화", n=4)
    assert len(copies) == 4
    assert all("title" in c and "highlight" in c for c in copies)


def test_suggest_thumbnail_no_key_raises():
    import os

    from cutdaejang.core.script_generator import ScriptError, suggest_thumbnail_copy

    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        with pytest.raises(ScriptError):
            suggest_thumbnail_copy("주제", api_key="")
    finally:
        if old:
            os.environ["GEMINI_API_KEY"] = old


@requires_ffmpeg
def test_make_thumbnail_16x9_from_image(tmp_path):
    from cutdaejang.core.thumbnail import make_thumbnail

    bg = tmp_path / "bg.png"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x1a3a6b:s=1000x1000", "-frames:v", "1", str(bg),
    ])
    out = make_thumbnail(str(bg), "사진만 넣으면\n홍보글이 뚝딱!", str(tmp_path / "thumb.png"),
                         highlight="뚝딱!")
    w, h = ff.probe_video_size(out)   # 이미지도 폭·높이 반환
    assert (w, h) == (1280, 720)      # 16:9 유튜브 썸네일


@requires_ffmpeg
def test_make_thumbnail_with_badge(tmp_path):
    from cutdaejang.core.thumbnail import make_thumbnail

    bg = tmp_path / "bg.png"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x1a3a6b:s=1280x720", "-frames:v", "1", str(bg),
    ])
    out = make_thumbnail(str(bg), "제목", str(tmp_path / "t.png"), badge="✅ 자동 발행")
    assert ff.probe_video_size(out) == (1280, 720)
    # 배지 스타일이 ass에 들어갔는지
    ass = (tmp_path / "thumb.ass").read_text(encoding="utf-8")
    assert "Badge,," in ass and "자동 발행" in ass


def test_denoise_filter_levels():
    from cutdaejang.core.edit_mode import _denoise_filter

    assert _denoise_filter(False) == ""
    assert "nr=18" in _denoise_filter(True)        # bool → 중간
    assert "nr=10" in _denoise_filter("low")
    assert "nr=30" in _denoise_filter("high")
    assert _denoise_filter("이상한값") == ""


@requires_ffmpeg
def test_make_thumbnail_from_video_frame(tmp_path):
    from cutdaejang.core.thumbnail import make_thumbnail

    vid = tmp_path / "v.mp4"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x203040:s=640x480:d=2:r=30",
        "-f", "lavfi", "-i", "anullsrc", "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid),
    ])
    out = make_thumbnail(str(vid), "제목 테스트", str(tmp_path / "t.png"))
    assert ff.probe_video_size(out) == (1280, 720)


@requires_ffmpeg
def test_thumbnail_presets_render_kmong_style(tmp_path):
    """v0.48 프리셋 — 임팩트(노랑 입체)·입체3D(빨강 기둥)가 실제 픽셀로 나오는지."""
    import subprocess

    from cutdaejang.core.thumbnail import make_thumbnail

    bg = tmp_path / "bg.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=0x1a4a6b:s=1280x720:d=0.1", "-frames:v", "1", str(bg)])

    def colors_at_band(png):
        # 중앙 밴드(글자 영역)를 1px 세로줄로 압축해 색 분포 확인
        raw = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-i", str(png),
             "-vf", "crop=800:300:240:210,scale=48:24", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]

    out1 = tmp_path / "임팩트.png"
    make_thumbnail(str(bg), "주말 딱 한 시간?\n스트레스 녹는 바다", str(out1),
                   preset="임팩트")
    px = colors_at_band(out1)
    assert any(r > 190 and g > 160 and b < 140 for r, g, b in px), "노랑 글자 없음"
    assert any(r < 60 and g < 60 and b < 60 for r, g, b in px), "검정 테두리/입체 없음"

    out2 = tmp_path / "입체3D.png"
    make_thumbnail(str(bg), "한 줄 제목 | 제목", str(out2), preset="입체3D")
    px2 = colors_at_band(out2)
    assert any(r > 170 and g < 90 and b < 90 for r, g, b in px2), "빨강 돌출 기둥 없음"
    assert any(r > 220 and g > 220 and b > 220 for r, g, b in px2), "흰 글자 없음"

    # 모르는 프리셋/깔끔은 기존(레거시) 경로로 안전
    out3 = tmp_path / "깔끔.png"
    make_thumbnail(str(bg), "깔끔 스타일", str(out3), preset="깔끔")
    assert out3.exists()
