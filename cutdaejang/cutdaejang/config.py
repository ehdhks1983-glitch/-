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
        "voice_elevenlabs": "",           # 내 목소리 클론 voice_id (등록 시 저장)
        "voice_elevenlabs_name": "",      # 표시용 이름
        "model_elevenlabs": "eleven_multilingual_v2",
        "sovits_url": "http://127.0.0.1:9880",  # GPT-SoVITS 로컬 API (무료 내 목소리)
        "sovits_ref_audio": "",                 # 참조 녹음(5~10초) 경로
        "sovits_ref_text": "",                  # 참조 녹음에서 말한 문장
        "windows_rate": 0,                      # 내장 음성 말 속도 -10~10 (v0.44)
        "auto_pronounce": True,                 # TTS 앞 숫자·영어 한글 발음 변환 (v0.46.1)
    },
    "audio": {
        "gap_ms": 220,                # 문장 간격
        "trim_threshold_db": -45,     # 무음 트림 임계값
        "edge_pad_ms": 30,            # 트림 후 앞뒤 무음 재부여
        "lufs": -16,
    },
    "watermark": {                    # 워터마크(로고) — 편집 폼에서 넣으면 기억됨
        "path": "",
        "pos": "tr",                  # tr(우상)/tl(좌상)/br(우하)/bl(좌하)
        "scale": 0.14,                # 캔버스 가로 대비 크기
        "opacity": 0.85,
    },
    "ui": {                           # 화면이 기억하는 것들
        "edit_last": {},              # 마지막 편집 폼 세팅 — 다음 실행 때 자동 복원 (v0.38)
        "templates": {},              # 이름 → 편집 폼 세팅 스냅샷 (v0.43 템플릿)
    },
    "channel": {                      # 📦 업로드 키트 맞춤용 내 채널 정보 (선택, v0.39)
        "name": "",
        "topic": "",
        "audience": "",
    },
    "bgm": {
        "enabled": False,
        "file": "",
        "volume_db": -20,
        "duck": True,                 # 목소리 나올 때 BGM 자동 감쇠 (v0.44 기본 켬)
    },
    "bg": {
        "motion": "zoom_in",          # zoom_in | zoom_out | off
        "motion_amount": 0.08,        # 총 줌 비율 (8%)
        "ai_image": True,             # AI 배경 (v0.45부터 기본 켬 — 키 없으면 자동 생략)
        "image_model": "gemini-2.5-flash-image",  # 정식명 (없으면 자동 폴백, v0.46.1)
        "scene_images": True,         # 문장(장면)마다 새 이미지 (v0.45. 끄면 1장+줌)
        "image_style": "일러스트",     # 장면 그림체 — background_generator.IMAGE_STYLES 키
        "character": "",              # 마스코트 캐릭터 (v0.50) — 프리셋 키 또는 직접 묘사
        "scene_mode": "auto",         # 장면 그림 방식 (v0.51): auto=AI 생성 | manual=내가 넣기 | off=끄기
        "max_scene_images": 0,        # 장면 그림 최대 장수 (v0.51) — 0=문장마다, N=N장만(비용 절감)
    },
    "subtitle": {
        "font_size": 84,             # 유튜브 쇼츠 기본 (v0.23 상향)
        "outline": 4,
        "shadow": 1,
        "margin_v": 480,              # 쇼츠 하단 UI(제목·버튼·진행바)에 안 가리는 높이
        "fade": True,
        "highlight_color": "#FFD400",
        "band": False,                # 자막 뒤 배경 띠 (유튜브 썸네일 스타일)
        "hook_band": True,            # 상단 제목 뒤 배경 띠 (기본 켬)
        "wrap_chars": 16,             # 자막 한 줄 최대 글자수(넘으면 2줄). 0=끔
        "anim": "none",               # 자막 등장 애니메이션: none | pop (v0.43)
        "hook_style": "기본",          # 상단 제목 프리셋 (v0.52): 기본|예능 노랑|화이트 박스|네온
        "sub_style": "기본",           # 본문 자막 프리셋 (v0.54): 기본|예능 노랑|말풍선 띠|네온
    },
    "branding": {                     # 인트로/아웃트로 (v0.43) — 영상 또는 사진 경로
        "intro": "",
        "outro": "",
    },
    "sfx": {                          # 🔔 효과음 자동 (v0.53) — 뿅(강조)·휙(전환)·띠링(제목)
        "enabled": True,
        "volume_db": -13,
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
            except (OSError, json.JSONDecodeError) as e:
                import logging  # noqa: PLC0415
                logging.getLogger("cutdaejang").warning(
                    "settings.json을 읽지 못해 기본값을 사용합니다 (%s): %s", candidate, e)
                continue  # 손상된 설정 파일은 무시하고 다음 후보/기본값
    return copy.deepcopy(DEFAULTS)


def _atomic_write(path: Path, text: str) -> None:
    """임시 파일에 쓰고 교체 — 저장 중 크래시로 파일이 잘리는 것 방지."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


CONFIG_VERSION = 2  # 저장 파일 스키마 표식 — 기본값이 바뀔 때 1회 승격용 (v0.50.1)


def migrate_settings(path: Optional[str] = None) -> list:
    """구버전 settings.json을 1회 승격 — 바뀐 기본값을 따라잡는다. 적용 내역 반환.

    v0.45에서 bg.ai_image 기본이 꺼짐→켬으로 바뀌었지만, 그 전에 설정 화면을
    저장한 파일에는 옛 false가 박제돼 AI 배경·장면 그림이 영영 안 나온다
    (사용자 리포트: "설정에서 AI 배경 꺼짐"). cfg_v 표식이 없는 파일 = 그 시절
    파일로 보고 켠다. 이후 저장은 항상 cfg_v가 찍히므로, 사용자가 직접 끈
    선택(cfg_v 있음)은 다시 건드리지 않는다.
    """
    target = _settings_target(path)
    if not target.is_file():
        return []
    try:
        user = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(user, dict) or user.get("cfg_v", 0) >= CONFIG_VERSION:
        return []
    applied = []
    bg = user.get("bg")
    if isinstance(bg, dict) and bg.get("ai_image") is False:
        bg["ai_image"] = True
        applied.append("AI 배경을 다시 켰습니다 (v0.45부터 기본 켬 — 원치 않으면 ⚙ 설정에서 끄기)")
    if isinstance(bg, dict) and bg.get("image_model") == "gemini-2.5-flash-image-preview":
        bg["image_model"] = DEFAULTS["bg"]["image_model"]  # 은퇴한 프리뷰명 → 정식명
        applied.append("이미지 모델명을 정식명으로 교체했습니다")
    user["cfg_v"] = CONFIG_VERSION
    try:
        _atomic_write(target, json.dumps(user, ensure_ascii=False, indent=2) + "\n")
    except OSError:
        return []
    return applied


def _settings_target(path: Optional[str] = None) -> Path:
    for candidate in _settings_candidates(path):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return project_root() / "settings.json"


def save_settings(overrides: dict, path: Optional[str] = None) -> str:
    """현재 설정에 overrides를 병합해 파일로 저장 (설정 화면용). 저장 경로 반환."""
    target = _settings_target(path)
    merged = deep_merge(load_settings(str(target) if target.is_file() else None), overrides)
    merged["cfg_v"] = CONFIG_VERSION  # 이후 이 파일은 마이그레이션이 건드리지 않음
    _atomic_write(target, json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
    return str(target)


def save_settings_replace(dotted_key: str, value, path: Optional[str] = None) -> str:
    """설정의 한 노드(예: "ui.templates")를 병합 없이 통째로 교체해 저장.

    deep_merge는 키를 지울 수 없어서 — 템플릿 삭제(v0.43) 같은 '빼기'는 이걸 쓴다.
    """
    target = _settings_target(path)
    merged = load_settings(str(target) if target.is_file() else None)
    node = merged
    parts = dotted_key.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value
    merged["cfg_v"] = CONFIG_VERSION
    _atomic_write(target, json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
    return str(target)


# ─────────── API 키 저장 (선택 기능 — 이 PC 파일에 평문 저장) ───────────

_KEY_ENVS = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
             "elevenlabs": "ELEVENLABS_API_KEY"}


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
    _atomic_write(path, json.dumps(keys, ensure_ascii=False, indent=2))


def clear_api_keys() -> None:
    api_keys_path().unlink(missing_ok=True)
    for env in _KEY_ENVS.values():
        os.environ.pop(env, None)
