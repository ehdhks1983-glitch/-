# 봇 클라이언트 통합 가이드

기존 봇(센텀라이터 등)에 `centumhi-license-client` 를 붙여 중앙 허브로 라이선스를
검증합니다. 자세한 검증 API 규격은 [`API.md`](API.md) 참고.

## 1. 설치

별도 저장소로 분리 전에는 경로/깃에서 설치할 수 있습니다.

```bash
pip install ./client            # 모노레포 경로
# 또는 (별도 저장소 분리 후)
# pip install git+https://github.com/ehdhks1983-glitch/centumhi-license-client.git
```

## 2. 시크릿 발급

1. 라이선스 허브 대시보드 → **제품 관리** 에서 해당 제품의 **HMAC 시크릿** 확인.
2. 봇 서버의 환경변수로 보관 (코드/깃에 절대 커밋 금지):
   ```bash
   export CENTUMHI_PRODUCT_CODE=centum-writer
   export CENTUMHI_PRODUCT_SECRET=...        # 대시보드에서 복사
   export CENTUMHI_SERVER_URL=https://api.license.centumhi.co.kr
   ```

## 3. 3줄 통합 (봇 시작 시)

```python
import os, sys
from centumhi_license import LicenseClient

client = LicenseClient(
    product_code=os.environ["CENTUMHI_PRODUCT_CODE"],
    product_secret=os.environ["CENTUMHI_PRODUCT_SECRET"],
    server_url=os.environ["CENTUMHI_SERVER_URL"],
)

result = client.verify_or_activate(user_input_key)   # 사용자가 입력한 키
if not result.valid:
    print(f"라이선스 오류: {result.reason}")
    sys.exit(1)

print(f"라이선스 정상 — 만료까지 {result.days_remaining}일")
```

## 4. 실행 중 주기적 체크 (선택)

```python
import threading, time

def license_watch(client, key, interval=3600):
    while True:
        time.sleep(interval)
        r = client.check(key)
        if not r.valid and not r.offline:
            print("라이선스가 더 이상 유효하지 않습니다:", r.reason)
            os._exit(1)

threading.Thread(target=license_watch, args=(client, user_input_key), daemon=True).start()
```

## 5. 동작 특성

- **HWID**: Windows는 `MachineGuid`, 그 외 OS는 MAC+호스트 해시로 자동 산출.
  기기당 등록 수는 제품/키의 `max_hwid_count` 로 제한.
- **오프라인 그레이스**: 서버 장애 시 마지막 성공 결과를 기본 7일간 캐시로 허용
  (`result.offline == True`). 캐시 위치는 `~/.centumhi/` (env `CENTUMHI_CACHE_DIR`).
- **재시도**: 일시적 네트워크 오류는 자동 재시도 후 그레이스 폴백.

## 6. 마이그레이션 (기존 발급 키)

기존에 개별 발급하던 키는 CSV(`product_code, key, plan_type, customer, expires_at`)로
정리한 뒤, 관리자 일괄 발급 또는 임포트 스크립트로 허브 DB에 등록합니다.
(임포트 스크립트는 Phase 4 후속 작업으로 제공 예정.)
