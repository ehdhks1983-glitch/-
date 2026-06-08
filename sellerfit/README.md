# SellerFit Slice 1 — 도매꾹 → 쿠팡 자동 등록

**도매꾹 상품번호 하나만 넣으면 쿠팡 판매자센터에 상품이 자동으로 등록되는 최소 파이프라인.**

v0.1 · 2026

---

## 📚 먼저 읽을 문서 (인수인계용)

| 문서 | 내용 |
|---|---|
| `CLAUDE.md` | **프로젝트 규칙 + 현재 상태** (Claude Code 자동 로드) |
| `docs/HANDOVER.md` | 배경, 의사결정 히스토리, 삽질 방지 |
| `docs/ROADMAP.md` | 완료분 + 향후 개발 계획 |
| `docs/ARCHITECTURE.md` | 코드 구조 상세 |
| `docs/CLAUDE_CODE_START.md` | Claude Code 작업 시작법 |
| `README.md` | (이 문서) 사용법 |

**Claude Code에서 작업 시작 → `docs/CLAUDE_CODE_START.md` 먼저 보세요.**

---

## 🎯 Slice 1 범위 (확정)

| 항목 | 결정 |
|---|---|
| 카테고리 | **쿠팡 카테고리 자동 추천 API** |
| 가격 책정 | **마진율 기반 3가지 모드** (`multiply`/`add_margin`/`min_margin`) |
| 이미지 | **도매꾹 URL → 접근성 검증 → 쿠팡에 전달** |
| 옵션 | **단일상품** (옵션 다건은 Slice 2) |
| 배송 | **선결제 고정** |
| 등록 상태 | **임시저장 기본** (`--request`로 즉시 승인요청 전환) |

---

## 📁 파일 구조

```
sellerfit_slice1/
├── config.py                    # 환경변수·설정 로드
├── logger.py                    # 로깅 (콘솔 컬러 + 파일)
├── data_snapshot.py             # 단계별 JSON 스냅샷 저장
├── domeggook_client.py          # 도매꾹 API 클라이언트
├── coupang_wing_client.py       # 쿠팡 WING API 클라이언트
├── coupang_metadata_collector.py  # 반품지/출고지 조회 + 캐시
├── category_mapper.py           # 카테고리 자동 매핑 + 캐시
├── pricing.py                   # 가격 계산 (3가지 모드)
├── image_pipeline.py            # 이미지 접근성 검증
├── payload_builder.py           # 쿠팡 상품 등록 JSON 조립
├── main.py                      # 🎯 CLI 진입점
├── requirements.txt
├── .env.example                 # 환경변수 템플릿
└── README.md                    # 이 문서
```

---

## 🚀 실행 절차

### 1. 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`을 `.env`로 복사 후 실제 값 입력:

```bash
cp .env.example .env
# 메모장이나 Cursor에서 .env 열어서 편집
```

최소 필수 3가지:
- `DOMEGGOOK_API_KEY`
- `COUPANG_WING_VENDOR_ID` (A로 시작)
- `COUPANG_WING_ACCESS_KEY`
- `COUPANG_WING_SECRET_KEY`

### 3. 사전 확인 (WING)

- ✅ **반품지** 1개 이상 등록 (WING → 판매자정보 → 주소지 관리)
- ✅ **출고지** 1개 이상 등록

### 4. 실행

```bash
# 현재 설정 확인
python main.py --config

# Dry-run (API 호출 없이 payload만 생성 - 안전 테스트)
python main.py 7914900 --dry-run

# 실제 등록 (임시저장 상태)
python main.py 7914900

# 등록 + 즉시 승인요청
python main.py 7914900 --request

# 브랜드 지정
python main.py 7914900 --brand "내브랜드"
```

---

## 🔄 파이프라인 8단계

```
[1] 쿠팡 메타데이터 수집    → 반품지/출고지 코드 확보 (24h 캐시)
[2] 도매꾹 상품 조회         → getItemView API → XML 파싱
[3] 가격 계산                → 도매가 → 판매가 (3모드 중 1)
[4] 카테고리 자동 매핑       → 쿠팡 predict API (결과 영구 캐시)
[5] 이미지 접근성 검증       → HEAD/GET으로 사용 가능한 URL만
[6] 쿠팡 Payload 조립        → Product Creation JSON
[7] 쿠팡 상품 등록 API 호출  → sellerProductId 획득
[8] 승인 요청 (선택)         → --request 플래그 시
```

각 단계의 **모든 데이터가 `snapshots/{상품번호}_{타임스탬프}/`** 에 JSON으로 저장돼서 문제 발생 시 추적 가능.

---

## 📊 가격 계산 3가지 모드

`.env`의 `PRICING_MODE` 값으로 선택.

### 1. `multiply` (기본)
```
판매가 = 도매가 × MULTIPLIER
예: 도매가 10,000원 × 2.5 = 25,000원
```

### 2. `add_margin`
```
판매가 = 도매가 × (1 + MARGIN_RATE/100)
예: 도매가 10,000원 × 1.5 = 15,000원 (마진 50%)
```

### 3. `min_margin`
```
판매가 = 도매가 / (1 - MIN_MARGIN/100)
예: 도매가 10,000원 / 0.7 = 14,285원 (마진 30% 보장)
```

모든 모드 공통:
- `PRICING_ROUND_TO` 단위 올림 (100원 / 1,000원 등)
- `PRICING_ADD_SHIPPING=true` 시 배송비를 원가에 포함

---

## 📸 스냅샷 구조

실행 1회마다 아래 폴더 생성:

```
snapshots/7914900_20260419_143022/
├── _summary.json                ← 전체 요약
├── 01_coupang_metadata.json     ← 반품지/출고지
├── 02_domeggook_raw.xml         ← 도매꾹 원본 XML
├── 02_domeggook_parsed.json     ← 정제된 상품 정보
├── 03_pricing.json              ← 가격 계산 내역
├── 04_category.json             ← 카테고리 매핑 결과
├── 05_images.json               ← 이미지 접근성 결과
├── 06_coupang_payload.json      ← 쿠팡 전송 JSON
├── 07_coupang_response.json     ← 쿠팡 응답
└── 08_approval_response.json    ← 승인요청 응답 (있으면)
```

**디버깅 꿀팁**: 뭔가 꺾이면 해당 단계 JSON 파일만 열어보면 바로 원인 파악.

---

## ⚠️ 알려진 제약 / TODO

### Slice 1 제약
- **옵션 다건** 미지원 (색상/사이즈 → items 1개로 축소)
- **고시정보** 카테고리 무관 '기타 재화' 하드코딩 (카테고리별 동적 로드는 Slice 2)
- **카테고리 필수 속성** (`attributes`) 빈 배열로 전송 → 일부 카테고리는 이걸로 등록 실패할 수 있음
- **이미지 자체 호스팅** 없음 (도매꾹 URL 직접 전달, 쿠팡이 거부하면 실패)

### 다음 Slice 계획
- Slice 2: 옵션 다건 + 카테고리 메타 반영 + Claude 카피 A/B
- Slice 3: CustomTkinter GUI + 일괄 처리
- Slice 4: 빌드/배포/라이선스

---

## 🐛 문제 진단

### "인증 실패" (401/403)
- VendorId 확인 (WING 우측 상단, `A`로 시작)
- Access/Secret Key 재발급
- WING에서 IP 등록 필요 여부 확인

### "반품지/출고지 0개"
- WING → 판매자정보 → 주소지 관리에서 먼저 등록

### "카테고리 추천 실패"
- 상품명이 너무 짧거나 모호할 가능성
- `cache/category_mapping.json` 에서 이전 시도 기록 확인

### "이미지 0장"
- `snapshots/.../02_domeggook_raw.xml` 열어서 실제 이미지 필드 확인
- 도매꾹 응답 구조가 상품 유형별로 다를 수 있음 → `domeggook_client._extract_images` 튜닝 필요

### "쿠팡 등록 400 에러"
- `snapshots/.../07_coupang_response.json` 에 쿠팡의 상세 에러 메시지 있음
- 가장 흔한 원인:
  - 필수 속성(attributes) 누락
  - 이미지 URL 접근 불가
  - 카테고리 코드 유효하지 않음

---

## 🔒 보안

- `.env` 파일은 **절대 Git 커밋 금지** (`.gitignore` 필수)
- `snapshots/` 폴더에는 **API 응답 원본이 포함**되므로 공유 시 주의
- Secret Key가 로그에 찍히지 않도록 `logger.py` 필터 적용됨

---

## 📝 다음 단계

이 Slice 1을 검토 → 수정 → 실제 상품 1개 등록 성공까지 확인되면:

1. **Slice 2 착수**: Claude 카피 + 템플릿 30종 + 옵션 다건
2. **Slice 3**: GUI + 일괄 처리
3. **Slice 4**: 빌드 + 배포

각 Slice 완료마다 **실제 쿠팡 등록 성공** 검증 후 다음으로.
