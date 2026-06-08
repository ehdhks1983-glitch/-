# SellerFit 코드 검토 결과 (2026-06-08)

> **읽는 법**: 이 문서는 `총기획안(MASTER PLAN)`의 리스크 레지스터 R1~R10을 **실제 코드와 대조**한 결과 + 기획안이 안 짚은 추가 발견입니다.
> 다음 세션(SellerFit repo) 시작 시 `총기획안` / `CLAUDE.md`와 함께 읽으세요. **Phase 0 작업 지도**로 쓰면 됩니다.
> 검토 시점에 **코드는 수정하지 않았습니다.** (도완님 원칙 1·검증 전 리팩토링 금지 준수)

---

## 한 줄 결론

기획안 진단은 대체로 정확. 아키텍처·스레딩·스냅샷·가격 3모드는 손댈 데 없음.
다만 기획안이 **R1·R9를 미묘하게 과소평가**했고, **리스트에 없는 실전 함정(B1~B4)**이 첫 등록에서 드러날 것.
가장 중요한 교정: **R1은 "이미지 0장 실패"보다 "엉뚱한 이미지로 조용히 등록 성공"이 더 위험하다.**

---

## A. 리스크 레지스터 R1~R10 — 코드 대조

| ID | 기획안 | 코드 검증 | 파일:줄 |
|---|---|---|---|
| **R1** 파서 XML 추측 | 🔴 높음 | ✅ 사실 + **더 위험** (아래) | `domeggook_client.py:257,281,290-303,227` |
| **R2** 쿠팡 이미지 다운로드 실패 | 🟠 보험 | ✅ 미구현 맞음. `final_url`=도매꾹 원본 | `pipeline_service.py:229`, `image_pipeline.py:133` |
| **R3** 고시정보 일괄 기타재화 | 🟠 중상 | ✅ `"기타 재화"` 하드코딩, 메타 안 읽음 | `payload_builder.py:293,284-305` |
| **R4** 카테고리 오분류 | 🟠 측정후 | ⚠️ confidence 계산만, **게이팅 0**. 기본값 "medium"라 무의미 | `category_mapper.py:121,155-169` |
| **R5** 숫자속성 500ml→1ml | 🟡 중 | ✅ 코드가 정확히 그 모양. NUMBER면 무조건 `"1"+단위` | `payload_builder.py:251-253,279` |
| **R6** 옵션 축소 | 🟠 상향 | ✅ 단일 `unitCount:1` 고정, `dome.options` 파싱만 하고 안 씀 | `payload_builder.py:167-216,195` |
| **R7** 키 IP 강제 | 🔴 검증필요 | 코드로 판단 불가(런타임). 실호출로만 확인 | — |
| **R8** 507줄 | 🟢 낮음 | ✅ 정확히 507줄 + 죽은 stub 주석 | `payload_builder.py:433-436` |
| **R9** HMAC 인코딩 | 🟡 중(잠재) | ✅ **실재 버그**. 서명/URL 인코더 불일치 (아래) | `coupang_wing_client.py:146 vs 160` |
| **R10** 테스트 0 | 🟡 중 | ✅ 각 모듈 `__main__` 스모크뿐, 테스트 파일 없음 | — |

### R1 — 기획안보다 한 단계 더 위험한 이유 (★우선)
추측 경로 12개가 다 빗나가면 정규식 폴백(`domeggook_client.py:316`)이 XML 속 **모든** 이미지 URL을 긁음 — 판매자 로고·배너·뱃지 포함.
그리고 `_build_images`가 `urls[0]`을 **대표이미지**로 박음(`payload_builder.py:328`).
`is_valid`(`domeggook_client.py:98`)는 "이미지 ≥1장"만 보므로 **쓰레기 이미지로도 통과**.
→ "0장 실패"는 안전한 케이스. **"로고가 대표이미지로 조용히 등록"이 진짜 함정.**
**Phase 0 첫 작업**: `02_domeggook_raw.xml` 실물 1건 받아서 `_parse_xml`·`_extract_images` 경로를 실제 태그로 고정.

### R9 — 정확한 진단 + 한 줄 수정
- 서명용 쿼리: `urlencode(params, quote_via=quote)` → 공백을 `%20` (`:146`)
- 실제 URL 쿼리: `urlencode(params)` → 기본 `quote_plus`로 공백을 `+` (`:160`)
- 둘이 달라 **공백/특수문자 파라미터에서 서명 불일치 → 401**.
- **현재는 안 터짐** (쓰는 파라미터가 전부 영숫자: vendorId·nextToken·pageNum…). 미래 검색/한글 파라미터에서 터짐.
- **수정(before/after)**: 같은 인코더로 만든 `query_str`을 서명과 URL **양쪽에 재사용**.
  ```python
  # before (:144-146, :159-160)
  query_str = ""
  if params:
      query_str = urlencode(params, quote_via=quote)
  ...
  if params:
      url += "?" + urlencode(params)        # ← quote_plus, 불일치

  # after
  query_str = urlencode(params, quote_via=quote) if params else ""
  ...
  if query_str:
      url += "?" + query_str                # ← 서명과 동일 바이트
  ```
  영향: `_request` 한 곳. 다른 기능 무영향. EXE 무관. 잔존리스크 낮음(현재 동작 동일, 미래 401 예방).

---

## B. 기획안에 없는 추가 발견

### Phase 0 실전 검증에 반드시 끼울 것 (첫 등록이 노출시킴)
- **B1. 상세 HTML을 `detailType:"TEXT"`로 주입** (`payload_builder.py:371-374`). "HTML→TEXT면 쿠팡이 렌더"는 **R1과 같은 미검증 가정**. 잘못되면 원본 HTML이 날 텍스트로 노출. `contentsType:"IMAGE_NO_SPACE"` 블록에 IMAGE+TEXT 혼합 → 거부 가능. **첫 등록 후 상세페이지 눈으로 확인.**
- **B2. 등록 성공을 실패로 오판** (`coupang_wing_client.py:58-65` + `pipeline_service.py:320`). `is_success`가 빡빡하고 `sellerProductId`를 `resp.data.get()`로만 추출. 쿠팡이 키 위치/형태 다르게 주면 **성공인데 spid=None**. 실제 `07_coupang_response.json` 보고 둘 다 보정 예상.
- **B3. `maximumBuyForPerson:"0"`** (`config.py:161`→`payload_builder.py:191`). 0이 "무제한"인지 "1인당 0개=구매불가"인지 쿠팡 스펙 확인. 후자면 등록은 되는데 **안 팔리는** 상품.
- **B4. 승인요청이 PUT** (`coupang_wing_client.py:340`). `--request` 시 메서드 맞는지 실호출 확인.

### 운영 전 정리 백로그 (낮음)
- **B5. 가짜 할인가**: `original_price = 판매가 × 1.2` (`pricing.py:50,97`). 근거 없는 "원가" 표시 → 원칙4 "과장 금지" + 표시광고 리스크. 의식적 결정인지 확인.
- **B6. 기본 반품지/출고지 = `[0]` 무조건** (`coupang_metadata_collector.py:86,97`). `usable` 받아놓고(`:132`) 안 씀 → 비활성 센터가 첫째면 전 상품 그걸로 등록. `usable==True` 우선 선택으로.
- **B7. 카테고리 캐시를 히트마다 디스크 전체 재기록** (`category_mapper.py:93`). Phase 4 대량(50~500개)에서 비효율 + 비원자적 쓰기 → 중단 시 캐시 손상. (temp 파일 → rename 권장)
- **B8. 없는 config 필드 참조**: `outboundShippingTimeDay`가 `self.reg.__dict__.get("outbound_days",2)` (`payload_builder.py:193`) → `outbound_days` 필드 없어 **항상 2 고정**. `maximum_buy_count`(`config.py:160`)도 정의만, 실제론 `stock_qty` 사용. 죽은 config 정리.
- **B9. EXE에서 `.env`**: `load_dotenv()`가 CWD 기준(`config.py:16`). frozen일 때 `load_dotenv(BASE_DIR/".env")` 명시 권장(원칙6). Phase 5 사안.

### 오해 방지 — 검증해보니 정상인 것
- `pipeline_service.py:367` `copy.copy(pricing_cfg)` 얕은 복사: 스칼라 필드뿐 → 전역 오염 없음. **정상.**
- GUI "다시 계산"이 도매꾹 재호출(`gui_app.py:300`): 쿼터 낭비지만 Slice1 허용 주석대로 의도됨.
- CLI는 `dome_category_path` 힌트를 mapper에 넘기나(`main.py:165`) GUI는 안 넘김(`pipeline_service.py:207`). 단 mapper가 그 힌트를 **안 쓰므로**(query에 저장만) 기능 차이 없음 — R4 개선 시 활용 여지.

---

## C. 건강해서 검증 전엔 건드리지 말 것 (원칙 1)
엔진/UI 분리 · 2단계(조회→등록) 서비스 레이어 · 전 단계 스냅샷 · 데몬스레드+`after()`+`queue` GUI · 가격 3모드(`pricing.py`, 안정) · HMAC 서명 로직 자체(인코딩만 제외하면 정확). R8(507줄 분리)도 **Phase 0 끝난 뒤**.

---

## D. Phase 0 시작 시 첫 액션 (순서)

**키 없이 지금 가능 (안전):**
1. R9 한 줄 수정 (위 before/after). before/after 보고 → 승인 → 적용.
2. B8 죽은 config 정리(`outbound_days` 실제 필드화 or 상수화, `maximum_buy_count` 제거).

**도완님 실제 키 5개 필요:**
3. `python main.py [상품번호] --dry-run` → `02_domeggook_raw.xml` 확보 → **R1 파서 경로 실측 고정** (이미지/옵션/가격 태그).
4. `06_coupang_payload.json` 검증 → 실제 등록 → `07_coupang_response.json`로 **B2(성공판정)·R3(고시정보)·B1(상세HTML)·B3(구매제한)** 보정.
5. **R7 확인**: 키 발급 IP를 호출마다 강제하는지 테스트 → 배포 모델(EXE 직배포 vs 중계서버) 결정.
6. 검증된 payload를 **골든 샘플**로 고정 (R10).

**DoD**: 실제 상품 1개가 쿠팡 임시저장에 에러 없이 등록 + 상세페이지 육안 정상 + R7 결론 도출.

---

*검토: 2026-06-08 / SellerFit zip(14개 모듈 3,598줄) 전수 대조 / 코드 미수정*
