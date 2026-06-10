"""
shorts_common.py — 쇼츠 엔진 공통 인프라
영상 규격(W, H)과 ffmpeg/ffprobe 실행·탐지 헬퍼. 다른 shorts_* 모듈이 공유한다.
(부록 A 분리: 분리 전 shorts_maker.py 상단의 공통 헬퍼를 그대로 옮긴 것 — 동작 동일)
"""

import subprocess
import sys
from pathlib import Path

from utils import find_ffmpeg

W, H = 1080, 1920  # 9:16 세로


# ════════════════════════════════════════
# 공통 실행 헬퍼
# ════════════════════════════════════════
def _run(cmd, timeout=300, cwd=None):
    kw = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": timeout}
    if cwd:
        kw["cwd"] = cwd
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kw["startupinfo"] = si
    return subprocess.run(cmd, **kw)


def _ffprobe_path() -> str:
    ff = find_ffmpeg()
    if ff:
        cand = str(Path(ff).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe"))
        if Path(cand).exists():
            return cand
    import shutil
    return shutil.which("ffprobe") or "ffprobe"


def _audio_duration(path: str) -> float:
    try:
        r = _run([_ffprobe_path(), "-v", "quiet", "-show_entries", "format=duration",
                  "-of", "csv=p=0", path], timeout=30)
        return float(r.stdout.decode().strip())
    except Exception:
        return 0.0


def _filter_available(ff: str, name: str) -> bool:
    """ffmpeg에 특정 필터(name)가 있는지 확인."""
    try:
        r = _run([ff, "-hide_banner", "-filters"], timeout=20)
        return name in (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return False
