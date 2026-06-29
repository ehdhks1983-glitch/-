# example_bot.py
# 내 봇에 라이선스 인증을 붙이는 예시.
# 아래 ★ 표시된 3줄을 "내 봇 코드 맨 위"에 넣으면 끝입니다.

# ── ★ 1) 불러오기 ──
from license_client import LicenseClient

# ── ★ 2) 클라이언트 만들기 ──
#   api_base : 서버 주소. 내 PC에서 돌리면 그대로, 인터넷에 올렸으면 그 주소로 변경.
#   bot_id   : 봇마다 다르게. 봇1→"bot1", 봇2→"bot2" ... 봇6→"bot6"
client = LicenseClient(api_base="http://localhost:3000", bot_id="bot1")

# ── ★ 3) 인증 통과해야 봇 실행 ──
ok, info = client.ensure_licensed()
if not ok:
    print("인증되지 않아 봇을 종료합니다.")
    raise SystemExit(1)

# ─────────────────────────────────────────────
# 여기서부터 원래 내 봇 코드 그대로 두면 됩니다.
# ─────────────────────────────────────────────
print("봇을 시작합니다! 🤖")

# 만료일/기기 정보가 필요하면 info 에서 꺼내 쓸 수 있어요.
if info and info.get("license"):
    lic = info["license"]
    print("만료:", lic.get("expires_at") or "무기한")
    print("기기:", f"{lic['devices']['used']}/{lic['devices']['max']}")

# ... 실제 봇 동작 ...
