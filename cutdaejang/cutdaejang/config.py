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
        "ai_image": False,            # AI 배경 이미지 생성 (opt-in, 실패 시 그라데이션 폴백)
        "image_model": "gemini-2.5-flash-image-preview",  # 모델 가용성 변동 대비 설정화
    },
    "subtitle": {
        "font_size": 76,
        "outline": 4,
        "shadow": 1,
        "margin_v": 420,              # 쇼츠 하단 UI(제목·버튼)와 안 겹치는 높이
        "fade": True,
        "highlight_color": "#FFD400",
        "band": False,                # 자막 뒤 배경 띠 (유튜브 썸네일 스타일)
        "hook_band": True,            # 상단 제목 뒤 배경 띠 (기본 켬)
    },
    "edit": {                         # 내 영상 편집 모드 (기획안 v1.5)
        "stt_provider": "whisper",   # whisper(로컬) | gemini | openai | stub
        "whisper_model": "small",
        "model_gemini": "gemini-2.5-flash",
        "noise_db": -30,             # 무음 판정 임계값
        "min_silence_s": 0.5,        # 이 이상 지속된 무음만 컷
        "pad_s": 0.10,               # 발화 앞뒤 여유
        "layout": "shorts",          # shorts(세로) | keep(원본 비율)
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


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _settings_candidates(path: Optional[str] = None) -> list:
    return [
        path,
        os.environ.get("CUTDAEJANG_SETTINGS"),
        "settings.json",
        str(project_root() / "settings.json"),
    ]


def load_settings(path: Optional[str] = None) -> dict:
    for candidate in _settings_candidates(path):
        if candidate and Path(candidate).is_file():
            try:
                user = json.loads(Path(candidate).read_text(encoding="utf-8"))
                return deep_merge(DEFAULTS, user)
            except (OSError, json.JSONDecodeError):
                continue  # 손상된 설정 파일은 무시하고 다음 후보/기본값
    return copy.deepcopy(DEFAULTS)


def save_settings(overrides: dict, path: Optional[str] = None) -> str:
    """현재 설정에 overrides를 병합해 파일로 저장 (설정 화면용). 저장 경로 반환."""
    target = None
    for candidate in _settings_candidates(path):
        if candidate and Path(candidate).is_file():
            target = Path(candidate)
            break
    target = target or (project_root() / "settings.json")
    merged = deep_merge(load_settings(str(target) if target.is_file() else None), overrides)
    target.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return str(target)


# ─────────── API 키 저장 (선택 기능 — 이 PC 파일에 평문 저장) ───────────

_KEY_ENVS = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


def api_keys_path() -> Path:
    return project_root() / "api_keys.json"


def load_api_keys_into_env() -> list:
    """저장된 키를 환경변수로 로드 (이미 설정돼 있으면 유지). 로드된 제공자 목록 반환."""
    loaded = []
    path = api_keys_path()
    if not path.is_file():
        return loaded
    try:
        keys = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return loaded
    for name, env in _KEY_ENVS.items():
        if keys.get(name) and not os.environ.get(env):
            os.environ[env] = str(keys[name])
            loaded.append(name)
    return loaded


def save_api_key(provider: str, key: str) -> None:
    path = api_keys_path()
    keys = {}
    if path.is_file():
        try:
            keys = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            keys = {}
    keys[provider] = key
    path.write_text(json.dumps(keys, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_api_keys() -> None:
    api_keys_path().unlink(missing_ok=True)
    for env in _KEY_ENVS.values():
        os.environ.pop(env, None)
