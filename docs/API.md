# API 가이드 (봇 클라이언트 통합)

Base URL (예): `https://api.license.centumhi.co.kr`
모든 응답은 JSON. 시간 값은 UTC ISO8601(`2026-07-03T11:14:21.317422Z`).

## 공통 에러 스키마

모든 처리된 오류는 동일한 형태로 응답합니다.

```json
{ "error_code": "invalid_signature", "message": "서명 검증에 실패했습니다.", "detail": null }
```

| 상황 | HTTP | error_code |
|---|---|---|
| 인증 필요 / 토큰 없음 | 401 | `unauthorized` |
| 토큰 무효·만료 | 401 | `invalid_token` |
| 관리자 전용 접근 | 403 | `forbidden` |
| 검증 서명 불일치 | 401 | `invalid_signature` |
| 타임스탬프 만료(재생) | 401 | `stale_timestamp` |
| 알 수 없는 제품 | 404 | `product_not_found` |
| 요청 형식 오류 | 422 | `validation_error` |

---

## 관리자/스탭 API (JWT)

`Authorization: Bearer <access_token>` 헤더 필요.

- `POST /api/auth/login` → `{ access_token, refresh_token, token_type }`
- `POST /api/auth/refresh` `{ refresh_token }` → `{ access_token }`
- `GET  /api/auth/me`
- `GET/POST/PATCH/DELETE /api/products` (관리자), `POST /api/products/{id}/rotate-secret`
- `GET /api/licenses` (필터: `product_id, status, expires_before, search, page, page_size`)
- `POST /api/licenses/issue` → 발급 (응답에 `raw_key` **1회만** 포함)
- `POST /api/licenses/issue-bulk?format=csv` → 일괄 발급 (JSON 또는 CSV)
- `POST /api/licenses/{id}/revoke`, `POST /api/licenses/{id}/extend`
- `DELETE /api/licenses/{id}/activations/{activation_id}` → HWID 해제
- `GET /api/stats/summary`, `GET /api/stats/revenue`

---

## 봇 검증 API (공개, HMAC 인증)

봇 클라이언트는 **제품별 시크릿(`secret_key`)** 으로 요청에 서명합니다.
시크릿은 관리자 대시보드의 제품 상세에서 확인하며, 봇 환경변수로만 보관하세요.

### 서명 규칙

```
message   = "{license_key}|{hwid}|{timestamp}"
signature = HMAC_SHA256(secret_key, message).hexdigest()   # 소문자 hex
timestamp = 현재 UNIX epoch(초).  서버 허용 오차 ±300초(기본).
```

### `POST /api/verify/activate` — 최초 활성화 (키 + HWID 등록)

요청:
```json
{
  "license_key": "CW-M30-NYAF2RDE-EW7KB6G7-DDWX",
  "hwid": "DESKTOP-ABC123",
  "product_code": "centum-writer",
  "client_version": "1.0.0",
  "timestamp": 1780485261,
  "signature": "9f1c…"
}
```
응답:
```json
{ "valid": true, "reason": null, "expires_at": "2026-07-03T11:14:21Z",
  "plan_type": "monthly_30", "max_hwid_count": 1, "days_remaining": 30 }
```
- 등록 가능한 HWID 수를 초과하면 `valid:false`, `reason:"등록 가능한 기기 수를 초과했습니다."`
- 취소/만료 키는 `valid:false`, `reason:"라이선스 상태: revoked"` 등.

### `POST /api/verify/check` — 실행 중 주기적 체크

요청: `{ license_key, hwid, product_code, timestamp, signature }` (activate와 동일 서명)
응답:
```json
{ "valid": true, "reason": null, "status": "active",
  "expires_at": "2026-07-03T11:14:21Z", "days_remaining": 30 }
```
- 등록되지 않은 HWID면 `valid:false` (재활성화 필요).

---

## 파이썬 서명 예시

```python
import hashlib, hmac, time, httpx

SECRET = "<제품 secret_key>"
SERVER = "https://api.license.centumhi.co.kr"

def sign(secret: str, *parts: str) -> str:
    msg = "|".join(parts).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

def activate(license_key: str, hwid: str, product_code: str):
    ts = int(time.time())
    body = {
        "license_key": license_key, "hwid": hwid, "product_code": product_code,
        "client_version": "1.0.0", "timestamp": ts,
        "signature": sign(SECRET, license_key, hwid, str(ts)),
    }
    return httpx.post(f"{SERVER}/api/verify/activate", json=body, timeout=10).json()
```

> Phase 4에서 이 로직을 `centumhi-license-client` 패키지로 제공할 예정입니다
> (HWID 자동 추출, 오프라인 그레이스 캐시, 재시도 포함).
