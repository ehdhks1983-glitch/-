"""설정 로딩 — settings.json (없으면 기본값) + 깊은 병합.

탐색 순서: 인자 경로 → 환경변수 CUTDAEJANG_SETTINGS → ./settings.json → 기본값.
사용자 경로·API 키는 여기 두지 않는다 (키는 환경변수/UI 입력).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Optional

DEFAULTS: dict = {
    "tts": {
        "rpm_limit": 8,               # 분당 호출 한도 (무료 등급 10의 80%)
        "max_retries": 5,
        "retry_wait_cap_s": 120,      # 문장당 재시도 총 대기 상한
        "fallback_chain": ["gemini", "openai"],
        "style_preset": "정보형",
        "voice_gemini": "Kore",
        "voice_openai": "nova",
        "model_gemini": "gemini-2.5-flash-preview-tts",
        "model_openai": "gpt-4o-mini-tts",
    },
    "audio": {
        "gap_ms": 220,                # 문장 간격
        "trim_threshold_db": -45,     # 무음 트림 임계값
        "edge_pad_ms": 30,            # 트림 후 앞뒤 무음 재부여
        "lufs": -16,
    },
    "bgm": {
        "enabled": False,
        "file": "",
        "volume_db": -20,
        "duck": False,
    },
    "bg": {
        "motion": "zoom_in",          # zoom_in | zoom_out | off
        "motion_amount": 0.08,        # 총 줌 비율 (8%)
    },
    "subtitle": {
        "font_size": 76,
        "outline": 4,
        "shadow": 1,
        "margin_v": 420,              # 쇼츠 하단 UI(제목·버튼)와 안 겹치는 높이
        "fade": True,
        "highlight_color": "#FFD400",
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(path: Optional[str] = None) -> dict:
    candidates = [
        path,
        os.environ.get("CUTDAEJANG_SETTINGS"),
        "settings.json",
        str(Path(__file__).resolve().parents[1] / "settings.json"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                user = json.loads(Path(candidate).read_text(encoding="utf-8"))
                return deep_merge(DEFAULTS, user)
            except (OSError, json.JSONDecodeError):
                continue  # 손상된 설정 파일은 무시하고 다음 후보/기본값
    return copy.deepcopy(DEFAULTS)
