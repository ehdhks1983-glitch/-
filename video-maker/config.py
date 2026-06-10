"""
config.py - 설정 관리
앱 전역 설정 + 마지막 사용 설정 저장/불러오기
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# ─── 앱 기본 정보 ───
APP_NAME = "영상 제작기"
APP_VERSION = "1.0.0"
WINDOW_SIZE = "1440x900"
MIN_WINDOW_SIZE = (1200, 780)

# ─── 자동 업데이트 ───
UPDATE_URL = "https://raw.githubusercontent.com/ehdhks1983-glitch/gifmaker-updates/main/version.json"

# ─── 경로 설정 ───
# 실행 파일(또는 스크립트)이 있는 폴더. ffmpeg 등 번들 바이너리의 기준 경로.
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent


def _user_data_dir(app_name: str) -> Path:
    """설정·로그·라이선스를 저장할 사용자 데이터 폴더(OS별).

    설치형(Program Files 등)에서는 BASE_DIR에 쓰기 권한이 없어 저장이 전부
    실패할 수 있으므로, 쓰기 가능한 사용자 AppData 영역을 기본 저장 위치로 쓴다.
      - Windows: %LOCALAPPDATA%/<app_name>
      - macOS:   ~/Library/Application Support/<app_name>
      - Linux:   $XDG_DATA_HOME/<app_name> (없으면 ~/.local/share/<app_name>)
    경로 계산에 실패하면 BASE_DIR/data 로 폴백한다.
    """
    try:
        if sys.platform == "win32":
            root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
            base = Path(root) if root else (Path.home() / "AppData" / "Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            root = os.getenv("XDG_DATA_HOME")
            base = Path(root) if root else (Path.home() / ".local" / "share")
        return base / app_name
    except Exception:
        return BASE_DIR / "data"


# 설정/로그/라이선스 저장 위치(AppData). FFmpeg 등 번들 바이너리는 BASE_DIR 사용.
DATA_DIR = _user_data_dir(APP_NAME)
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # AppData 생성 실패 시 최후 폴백 — 실행 폴더 하위 data
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
