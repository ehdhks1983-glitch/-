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
