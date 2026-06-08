# SellerFit 아키텍처 문서

> 코드 구조를 깊이 이해하기 위한 문서. 수정 작업 전 읽으면 영향도 파악이 쉬움.

---

## 레이어 구조

```
┌─────────────────────────────────────────────┐
│  UI 레이어                                    │
│  - gui_app.py     (CustomTkinter GUI)        │
│  - main.py        (CLI)                      │
└──────────────┬──────────────────────────────┘
               │ 호출
┌──────────────▼──────────────────────────────┐
│  서비스 레이어                                │
│  - pipeline_service.py  (조회/등록 분리)      │
│    · SellerFitService                        │
│    · PreparedProduct (조회결과 DTO)          │
└──────────────┬──────────────────────────────┘
               │ 조합
┌──────────────▼──────────────────────────────┐
│  엔진 레이어 (UI를 모름, 재사용 가능)          │
│  - domeggook_client.py     도매꾹 API        │
│  - coupang_wing_client.py  쿠팡 API          │
│  - coupang_metadata_collector.py  반품지등   │
│  - category_mapper.py      카테고리          │
│  - pricing.py              가격계산          │
│  - image_pipeline.py       이미지            │
│  - payload_builder.py      쿠팡 JSON 조립    │
└──────────────┬──────────────────────────────┘
               │ 공통 사용
┌──────────────▼──────────────────────────────┐
│  인프라 레이어                                │
│  - config.py        설정/환경변수            │
│  - logger.py        로깅                     │
│  - data_snapshot.py 단계별 저장              │
└─────────────────────────────────────────────┘
```

**의존성 방향**: 위 → 아래로만. 엔진은 UI를 import하지 않음 (그래서 CLI/GUI 양쪽에서 재사용).

---

## 주요 클래스/데이터 구조

### DomeggookProduct (domeggook_client.py)
도매꾹 상품 정보 DTO.
```python
item_no, title, keywords, tier_prices, supply_price,
images[], options[], description_html, ...
@property base_price   # 가격계산 기준가
@property is_valid     # 등록 가능 여부 (제목+가격+이미지 있나)
```

### PreparedProduct (pipeline_service.py)
조회 단계 결과. GUI 표시 + 등록에 재사용.
```python
ok, error, dome_product, title, base_price,
pricing, sale_price, category_code, usable_image_urls,
return_center, outbound_center, payload, _snap
```

### WingResponse (coupang_wing_client.py)
쿠팡 API 응답 래퍼.
```python
status_code, body
@property is_success, data, message, error_summary
```

### PricingResult (pricing.py)
가격 계산 결과 + 상세 내역.
```python
dome_base_price, cost, sale_price, original_price,
margin_amount, margin_rate, mode
```

---

## 핵심 흐름 상세

### 조회 (fetch_product)
```
1. check_environment()        → API키 + 반품지/출고지 (캐시)
2. dome_client.get_item_view  → DomeggookProduct
   → 실패: is_valid False면 중단
3. PriceCalculator.calculate  → PricingResult
4. category_mapper.get_category → displayCategoryCode
4b. wing_client.get_required_attributes → 필수옵션 리스트
5. image_pipeline.process     → 사용가능 URL
6. payload_builder.build      → 쿠팡 JSON
   → validate_payload (하드에러) + get_payload_warnings (소프트경고)
```

### 등록 (register_product)
```
7. wing_client.create_product(payload) → sellerProductId
8. (선택) wing_client.request_approval → 승인요청
→ snapshot.finalize
```

---

## 쿠팡 API 핵심 지식 (payload_builder 수정 시 필독)

### 인증 (절대 건드리지 말 것)
- HMAC-SHA256
- message = `{datetime}{METHOD}{PATH}{QUERY}`
- 헤더: `Authorization: CEA algorithm=...` + `X-Requested-By: {vendorId}`

### 상품 생성 payload 필수 필드
최상위: displayCategoryCode, sellerProductName, vendorId, saleStartedAt,
saleEndedAt, displayProductName, brand, deliveryMethod, deliveryCompanyCode,
deliveryChargeType, returnCenterCode, outboundShippingPlaceCode, **vendorUserId**, items[]

item 레벨: itemName, originalPrice, salePrice, images[], **attributes[]**,
**notices[]**, contents[], maximumBuyCount, ...

### ⚠️ 자주 거부되는 이유
1. **attributes 빈 배열** → "필수 구매옵션 없음" (카테고리 메타로 채워야)
   - `required=="MANDATORY"` 또는 `exposed=="EXPOSED"` 속성은 필수
   - 생성 형식: `{"attributeTypeName":"수량", "attributeValueName":"1개"}`
2. vendorUserId 누락
3. 이미지 URL 접근 불가 (쿠팡이 못 가져옴)
4. 카테고리 코드 유효하지 않음

### 도매꾹 API 핵심
- getItemView: 상품 1개 상세
- EUC-KR 인코딩 (응답 자동 감지)
- 분당 180회 / 일 15,000회 제한
- 이미지 경로가 공식 문서에 불명확 → 여러 경로 시도 + 정규식 폴백

---

## 캐시 시스템

| 캐시 | 파일 | TTL | 용도 |
|---|---|---|---|
| 쿠팡 메타 | `cache/coupang_metadata.json` | 24시간 | 반품지/출고지 |
| 카테고리 | `cache/category_mapping.json` | 영구 | 상품명→카테고리 매핑 |

---

## 스냅샷 시스템

실행마다 `snapshots/{상품번호}_{타임스탬프}/` 생성:
- 각 단계 JSON + 도매꾹 원본 XML
- `_summary.json` (전체 요약)
- 디버깅: 어느 단계에서 깨졌는지 추적
- 재시작: 직전 단계부터 재개 가능 (현재는 수동)

---

## 확장 포인트 (다음 작업 시)

### 대량 등록 추가 시
- `pipeline_service.py`에 배치 메서드
- 기존 `fetch_product` + `register_product` 반복 호출
- throttle (도매꾹 분당 180회)

### AI 카피 추가 시
- 새 모듈 `ai_copywriter.py`
- `payload_builder._build_contents`에서 호출
- Claude API 키 config에 추가

### 옵션 다건 추가 시
- `payload_builder._build_items` 다건 대응
- `domeggook_client` 옵션 파싱 정교화
