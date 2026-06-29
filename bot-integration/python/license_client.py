# license_client.py
# 파이썬 봇용 통합 라이선스 검증 클라이언트.
# 추가 설치(pip) 필요 없음 — 파이썬 표준 라이브러리만 사용합니다.
#
# 봇 코드에 단 3줄만 추가하면 됩니다:
#
#     from license_client import LicenseClient
#     client = LicenseClient(api_base="http://localhost:3000", bot_id="bot1")
#     if not client.ensure_licensed()[0]:
#         raise SystemExit("인증되지 않았습니다.")
#
# (api_base 는 서버 주소, bot_id 는 봇마다 bot1~bot6 으로 바꿔주세요.)

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


def get_device_id() -> str:
    """이 PC를 안정적으로 식별하는 지문(매번 같은 값). 윈도우 MachineGuid 우선."""
    # 1) 윈도우: 레지스트리 MachineGuid (가장 안정적)
    try:
        import winreg  # 윈도우에서만 존재

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return hashlib.sha256(guid.encode()).hexdigest()[:32]
    except Exception:
        pass
    # 2) 폴백: 네트워크 카드 MAC 주소 기반 해시
    return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]


class LicenseClient:
    def __init__(
        self,
        api_base: str = "http://localhost:3000",
        bot_id: str = "bot1",
        key_file: str | None = None,
        timeout: int = 10,
    ):
        self.api_base = api_base.rstrip("/")
        self.bot_id = bot_id
        self.timeout = timeout
        self.device_id = get_device_id()
        self.key_file = key_file or self._default_key_path()

    # ── 코드 저장/불러오기 (한 번 입력하면 다음부턴 자동) ──
    def _default_key_path(self) -> str:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "MyBots")
        os.makedirs(folder, exist_ok=True)
        # 봇마다 코드를 따로 저장(원하면 공유하도록 bot_id 제거 가능)
        return os.path.join(folder, f"license_{self.bot_id}.key")

    def _load_saved(self) -> str:
        try:
            with open(self.key_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def _save(self, code: str) -> None:
        try:
            with open(self.key_file, "w", encoding="utf-8") as f:
                f.write(code.strip())
        except OSError:
            pass  # 저장 실패해도 검증 자체엔 지장 없음

    # ── 서버 검증 ──
    def verify(self, code: str) -> dict:
        """서버에 코드를 검증한다. 항상 dict 를 돌려준다(valid, reason, message...)."""
        payload = json.dumps(
            {
                "code": code,
                "device_id": self.device_id,
                "bot_id": self.bot_id,
                "device_label": os.environ.get("COMPUTERNAME", ""),
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base}/api/license/verify",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 400/429/503/500 등 — 본문에 메시지가 있으면 그대로 전달
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"valid": False, "reason": "http_error", "message": f"서버 오류({e.code})"}
        except urllib.error.URLError as e:
            return {
                "valid": False,
                "reason": "network_error",
                "message": f"서버에 연결할 수 없습니다: {e.reason}",
            }
        except Exception as e:  # noqa: BLE001
            return {"valid": False, "reason": "unknown", "message": str(e)}

    # ── 봇 시작 시 호출하는 메인 진입점 ──
    def ensure_licensed(self, max_attempts: int = 3) -> tuple[bool, dict | None]:
        """
        저장된 코드로 먼저 검증 → 실패 시 콘솔로 코드 입력을 받는다.
        반환: (통과여부, 라이선스정보 dict | None)
        """
        saved = self._load_saved()
        if saved:
            r = self.verify(saved)
            if r.get("valid"):
                return True, r
            # 정지/만료 등 명확한 거절이면 저장된 코드 제거
            if r.get("reason") in ("revoked", "expired", "not_found", "device_limit"):
                self._save("")
            else:
                # 네트워크 오류 등 일시적 문제면 알려주고 재입력은 받지 않음
                print(f"[라이선스] {r.get('message')}")

        # 콘솔 입력이 불가능한 환경(창 없는 실행)이면 여기서 종료
        if not sys.stdin or not sys.stdin.isatty():
            return False, None

        for _ in range(max_attempts):
            code = input("인증코드를 입력하세요 (예: ALLB-XXXXX-XXXXX-XXXXX): ").strip()
            if not code:
                continue
            r = self.verify(code)
            if r.get("valid"):
                self._save(code)
                print("✅ 인증 완료!")
                return True, r
            print(f"❌ 인증 실패: {r.get('message')}")
        return False, None
