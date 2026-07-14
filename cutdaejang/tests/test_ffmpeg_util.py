"""run_with_progress stderr 데드락 회귀 테스트 (사용자 렌더 0% 정지 리포트).

stdout(진행률)만 읽고 stderr를 방치하면 파이프 버퍼가 차서 ffmpeg가 멈추는 고전 버그.
stderr를 별도 스레드로 동시에 비워야 한다.
"""

import pytest

from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def test_run_with_progress_no_deadlock_under_heavy_stderr(tmp_path):
    # -loglevel verbose로 내장 error를 덮어써 stderr를 대량 발생시켜도 완료돼야 함
    out = tmp_path / "o.mp4"
    progs = []
    ff.run_with_progress(
        [
            "-y", "-loglevel", "verbose",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=4",
            "-c:v", "libx264", "-preset", "veryfast", str(out),
        ],
        total_us=4_000_000,
        progress_cb=progs.append,
    )
    assert out.exists()
    assert progs and progs[-1] == pytest.approx(1.0)  # 100%까지 진행


def test_run_with_progress_raises_with_stderr_tail_on_failure(tmp_path):
    # 존재하지 않는 입력 → 실패, 오류 텍스트(stderr 꼬리)가 예외에 담겨야 함
    with pytest.raises(ff.FFmpegError, match="렌더 실패"):
        ff.run_with_progress(
            ["-i", str(tmp_path / "does_not_exist.mp4"), "-f", "null", "-"],
            total_us=1_000_000,
        )
