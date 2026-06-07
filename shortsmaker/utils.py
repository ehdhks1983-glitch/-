"""
utils.py - 공통 유틸리티
파일 처리, FFmpeg 감지, 포맷 헬퍼 등
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

from config import FFMPEG_EXE, FFPROBE_EXE, BASE_DIR

# ─── 지원 포맷 ───
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp', '.gif'}
VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv'}
OUTPUT_FORMATS = ['gif', 'webp', 'apng']

# ─── FFmpeg 경로 관리 ───
_ffmpeg_path: Optional[str] = None
_ffprobe_path: Optional[str] = None


def find_ffmpeg() -> Optional[str]:
    """FFmpeg 실행 파일 경로를 찾는다 (내장 → 시스템 PATH 순서)"""
    global _ffmpeg_path
    if _ffmpeg_path:
        return _ffmpeg_path

    # 1) 내장 바이너리
    if FFMPEG_EXE.exists():
        _ffmpeg_path = str(FFMPEG_EXE)
        return _ffmpeg_path

    # 2) 시스템 PATH
    found = shutil.which("ffmpeg")
    if found:
        _ffmpeg_path = found
        return _ffmpeg_path

    return None


def find_ffprobe() -> Optional[str]:
    global _ffprobe_path
    if _ffprobe_path:
        return _ffprobe_path

    if FFPROBE_EXE.exists():
        _ffprobe_path = str(FFPROBE_EXE)
        return _ffprobe_path

    found = shutil.which("ffprobe")
    if found:
        _ffprobe_path = found
        return _ffprobe_path

    return None


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def run_ffmpeg(args: list, timeout: int = 300) -> subprocess.CompletedProcess:
    """FFmpeg 명령 실행 (창 숨김 처리 포함)"""
    ff = find_ffmpeg()
    if not ff:
        raise FileNotFoundError("FFmpeg를 찾을 수 없습니다.")

    cmd = [ff] + args

    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": timeout,
    }
    # Windows: 콘솔 창 숨기기
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si

    return subprocess.run(cmd, **kwargs)


# ─── 파일명 생성 ───
def generate_output_name(
    base_name: str = "output",
    ext: str = "gif",
    output_dir: str = ""
) -> str:
    """중복 방지 파일명 생성 (output_날짜_시간_001.gif)"""
    if not output_dir:
        output_dir = str(Path.home() / "Desktop")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{base_name}_{timestamp}.{ext}"
    full = out_dir / name

    if not full.exists():
        return str(full)

    # 넘버링
    for i in range(1, 1000):
        name = f"{base_name}_{timestamp}_{i:03d}.{ext}"
        full = out_dir / name
        if not full.exists():
            return str(full)

    return str(full)


def is_image_file(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def format_filesize(size_bytes: int) -> str:
    """바이트 → 사람 읽기 좋은 문자열"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_image_info(path: str) -> Optional[Tuple[int, int, str]]:
    """이미지 정보 반환: (width, height, format)"""
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.width, img.height, img.format or "UNKNOWN"
    except Exception:
        return None


def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))
