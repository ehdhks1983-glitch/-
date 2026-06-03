# centumhi-license-client

센텀하이 라이선스 허브용 봇 클라이언트. 기존 봇에 `pip install` + 3줄로 통합.

```python
from centumhi_license import LicenseClient

client = LicenseClient(
    product_code="centum-writer",
    product_secret="<제품 secret_key, env에서 로드>",
    server_url="https://api.license.centumhi.co.kr",
)

result = client.verify_or_activate("CW-M30-XXXX-XXXX-XXXX")
if not result.valid:
    print(f"라이선스 오류: {result.reason}")
    raise SystemExit(1)

print(f"만료까지 {result.days_remaining}일 남음")
```

## 특징
- **HWID 자동 추출**: Windows `MachineGuid` 우선, 그 외 OS는 MAC+호스트 해시.
- **HMAC 서명 자동 생성**: 제품 시크릿으로 요청 서명.
- **오프라인 그레이스**: 네트워크 장애 시 마지막 성공 결과를 기본 7일간 캐시로 허용.
- **재시도**: 일시적 네트워크 오류 자동 재시도.
- 런타임 의존성은 `requests` 하나뿐.

## API
- `client.verify_or_activate(license_key)` — 봇 시작 시 1회. HWID 등록 + 검증.
- `client.check(license_key)` — 실행 중 주기적 체크.
- 반환값 `VerifyResult`: `valid, reason, status, plan_type, expires_at, days_remaining, max_hwid_count, offline`.

## 캐시 위치
기본 `~/.centumhi/`. 환경변수 `CENTUMHI_CACHE_DIR`로 변경 가능.
