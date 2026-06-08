"""
config.py - 설정 관리
앱 전역 설정 + 마지막 사용 설정 저장/불러오기
"""

import json
from pathlib import Path
from typing import Any, Dict

# ─── 앱 기본 정보 ───
APP_NAME = "GIF Maker Pro"
APP_VERSION = "1.9.1"
WINDOW_SIZE = "1440x900"
MIN_WINDOW_SIZE = (1200, 780)

# ─── 자동 업데이트 ───
UPDATE_URL = "https://raw.githubusercontent.com/ehdhks1983-glitch/gifmaker-updates/main/version.json"

# ─── 경로 설정 ───
if getattr(__import__('sys'), 'frozen', False):
    import sys
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

# ─── FFmpeg 경로 ───
FFMPEG_DIR = BASE_DIR / "ffmpeg"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_DIR / "ffprobe.exe"

# ─── 기본 설정값 ───
DEFAULTS: Dict[str, Any] = {
    # 이미지 합치기
    "merge_output_format": "gif",       # gif / webp / apng
    "merge_fps": 10,
    "merge_delay_ms": 100,              # 프레임 딜레이 (밀리초)
    "merge_loop": 0,                    # 0=무한, 1=한번, N=N회
    "merge_resize_mode": "largest",     # largest / smallest / custom
    "merge_custom_width": 800,
    "merge_custom_height": 600,
    "merge_bg_color": "#000000",
    "merge_quality": 85,                # WebP 품질

    # 영상 변환 (3단계에서 사용)
    "video_output_format": "gif",
    "video_fps": 15,
    "video_resolution": "original",
    "video_quality": 80,
    "video_quality_mode": "🔵 균형",
    "video_speed": 1.0,
    "video_loop": 0,

    # 녹화 (4단계에서 사용)
    "record_fps": 15,
    "record_output_format": "gif",
    "record_resolution_scale": 100,

    # 공통
    "output_dir": str(Path.home() / "Desktop"),
    "theme": "dark",
    "last_input_dir": "",
}


class Settings:
    """JSON 파일 기반 설정 관리"""

    def __init__(self):
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            if SETTINGS_FILE.exists():
                saved = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
                self._data.update(saved)
        except Exception:
            pass  # 파일 손상 시 기본값 유지

    def save(self):
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception:
            pass

    def get(self, key: str, default=None) -> Any:
        return self._data.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        self._data[key] = value

    def reset(self):
        self._data = dict(DEFAULTS)
        self.save()


# 전역 싱글턴
settings = Settings()
