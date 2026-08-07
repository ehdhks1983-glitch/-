"""🔑 정품 코드 + 7일 무료 체험 (v1.49 목록 99).

회원님 49차: "기본은 7일 무료로 쓸 수 있게 해야 하고, 내가 날짜를 넣을 수
있는 코드를 넣어야 해."

■ 정품 코드 형식:  CD-YYYYMMDD-XXXXXXXXXXXX
   · 앞의 YYYYMMDD = 이 코드가 «유효한 마지막 날» (판매자가 지정)
   · 뒤 12자 = 서명 (HMAC-SHA256 base32). 비밀 열쇠를 아는 사람만 만들 수 있다.
   · 코드는 「만료일 + 랜덤 시드」에 서명한다 — 같은 날짜라도 매번 다른 코드가
     나와 재판매 추적이 된다.

■ 서명 방식과 정직한 한계:
   제품이 순수 파이썬 소스라, 비밀 열쇠를 완벽히 숨길 수는 없다(난독화는
   casual 추출만 막는다). 이 방식은 «일반 회원의 무단 공유»를 막는 실용적
   수준이고, 완전한 복제 방지는 서버 인증이 필요하다(운영 부담이 커 이번엔
   넣지 않는다). 코드 «생성기»(make_license.py)는 제품에 넣지 않는다 —
   저장소 루트의 판매자 전용 도구다.

■ 7일 체험: 첫 실행일을 두 곳(settings + 홈 숨김 파일)에 적어 하나를 지워도
   남게 하고, 시계를 뒤로 돌리면(마지막 실행일보다 과거) 눈치챈다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import date, datetime, timezone
from pathlib import Path

from .. import config

TRIAL_DAYS = 7
_CODE_PREFIX = "CD"
_SIG_LEN = 12  # base32 문자 수 (60비트 — 무작위 위조 성공률 2^-60)

# 🔒 제품 검증 열쇠 (난독화). 마스크는 파생 상수라 소스에 hex가 그대로 안 보인다.
#    HMAC은 대칭이라 이 열쇠로 서명도 만들 수 있다 — 그래서 casual 추출만 막는다.
_OBF = bytes.fromhex(
    "d080b05ae92b7736059bf00ed1e958a8f7fd12ee6d9b2412943399232467dafa")


def _secret() -> bytes:
    mask = hashlib.sha256(b"cutdaejang-license-v1-mask").digest()
    return bytes(a ^ b for a, b in zip(_OBF, mask))


def _sign(expiry: str, seed: str) -> str:
    """만료일(YYYYMMDD) + 시드 → 12자 base32 서명."""
    msg = f"{expiry}:{seed}".encode()
    mac = hmac.new(_secret(), msg, hashlib.sha256).digest()
    return base64.b32encode(mac).decode("ascii").rstrip("=")[:_SIG_LEN]


def make_code(expiry: str, seed: str) -> str:
    """정품 코드 조립 — 생성기(판매자)와 검증(제품)이 같은 규칙을 쓴다."""
    return f"{_CODE_PREFIX}-{expiry}-{seed}{_sign(expiry, seed)}"


def _parse(code: str):
    """코드 → (만료 date, 원문 서명부) 또는 None (형식 불량)."""
    parts = (code or "").strip().upper().replace(" ", "").split("-")
    if len(parts) != 3 or parts[0] != _CODE_PREFIX:
        return None
    expiry, tail = parts[1], parts[2]
    if len(expiry) != 8 or not expiry.isdigit() or len(tail) <= _SIG_LEN:
        return None
    seed, sig = tail[:-_SIG_LEN], tail[-_SIG_LEN:]
    try:
        exp_date = datetime.strptime(expiry, "%Y%m%d").date()
    except ValueError:
        return None
    return expiry, seed, sig, exp_date


def verify_code(code: str, today: date | None = None) -> dict:
    """정품 코드 검증 → {"valid", "reason", "expiry"(ISO 또는 "")}.

    valid=True면 today가 만료일 이하다. 서명이 틀리면 valid=False·reason="위조".
    """
    today = today or _today()
    p = _parse(code)
    if not p:
        return {"valid": False, "reason": "형식이 올바르지 않아요 (CD-날짜-코드)",
                "expiry": ""}
    expiry, seed, sig, exp_date = p
    if not hmac.compare_digest(sig, _sign(expiry, seed)):
        return {"valid": False, "reason": "코드가 올바르지 않아요 (위조·오타)",
                "expiry": ""}
    if today > exp_date:
        return {"valid": False, "reason": f"이 코드는 {exp_date.isoformat()}까지였어요",
                "expiry": exp_date.isoformat()}
    return {"valid": True, "reason": "", "expiry": exp_date.isoformat()}


# ── 7일 체험 ────────────────────────────────────────────────────
def _today() -> date:
    return datetime.now(timezone.utc).astimezone().date()


def _shadow_path() -> Path:
    # settings.json을 지워도 남는 두 번째 기록 (사용자 홈의 숨김 파일)
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") \
        or str(Path.home())
    return Path(base) / ".cutdaejang_fp"


def _read_shadow() -> dict:
    try:
        import json  # noqa: PLC0415
        return json.loads(_shadow_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_shadow(d: dict) -> None:
    try:
        import json  # noqa: PLC0415
        p = _shadow_path()
        p.write_text(json.dumps(d), encoding="utf-8")
        if os.name == "nt":               # 숨김 속성 (실패해도 무방)
            os.system(f'attrib +h "{p}" >nul 2>&1')
    except Exception:  # noqa: BLE001
        pass


def mark_first_run() -> None:
    """첫 실행일을 두 곳에 적는다 (없을 때만). 매 실행마다 «마지막 본 날»도 갱신."""
    today = _today().isoformat()
    st = config.load_settings()
    lic = dict(st.get("license") or {})
    sh = _read_shadow()
    first = lic.get("first_run") or sh.get("first_run") or today
    seen = [d for d in (lic.get("last_seen"), sh.get("last_seen")) if d]
    last_seen = max(seen) if seen else today       # 가장 최근 기록
    new_seen = max(last_seen, today)               # 시계를 되돌려도 최댓값 유지
    payload = {"first_run": first, "last_seen": new_seen}
    if today < last_seen:                          # 시계 되돌림 감지
        payload["clock_back"] = True
    config.save_settings({"license": payload})
    _write_shadow(payload)


def status() -> dict:
    """지금 사용 자격 → {"licensed", "trial", "days_left", "expiry", "reason"}.

    · licensed=True: 유효한 정품 코드가 저장돼 있다 (체험과 무관)
    · trial=True: 체험 기간 안 (licensed가 아닐 때만 의미)
    · 둘 다 False면 잠금 (첫 화면에서 코드 요구)
    """
    today = _today()
    st = config.load_settings()
    lic = dict(st.get("license") or {})
    sh = _read_shadow()

    code = lic.get("code") or ""
    if code:
        v = verify_code(code, today)
        if v["valid"]:
            return {"licensed": True, "trial": False, "days_left": None,
                    "expiry": v["expiry"], "reason": ""}

    first_iso = lic.get("first_run") or sh.get("first_run") or today.isoformat()
    try:
        first = date.fromisoformat(first_iso)
    except ValueError:
        first = today
    used = (today - first).days
    # 시계를 되돌린 흔적이 있으면 체험을 소진된 것으로 본다 (관대하게: 잠그진 않고 표시)
    clock_back = bool(lic.get("clock_back") or sh.get("clock_back"))
    days_left = max(0, TRIAL_DAYS - used)
    if clock_back:
        days_left = 0
    return {"licensed": False, "trial": days_left > 0, "days_left": days_left,
            "expiry": "", "reason": ("시계가 되돌려진 것 같아요" if clock_back else "")}


def save_code(code: str) -> dict:
    """입력한 코드를 검증하고 유효하면 저장 → status()와 같은 형태 반환."""
    v = verify_code(code)
    if not v["valid"]:
        return {"ok": False, "reason": v["reason"]}
    config.save_settings({"license": {"code": code.strip().upper()}})
    return {"ok": True, "expiry": v["expiry"]}
