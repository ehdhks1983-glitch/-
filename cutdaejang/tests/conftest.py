import shutil

import pytest

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe 필요",
)


@pytest.fixture
def make_sine_clip(tmp_path):
    """지정 길이의 사인파 m4a 생성 (TTS 클립 대역)."""
    from cutdaejang.utils import ffmpeg as ff

    def _make(name: str, seconds: float, freq: int = 440):
        out = tmp_path / name
        ff.run(
            [
                ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds:.3f}",
                "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(out),
            ]
        )
        return out

    return _make
