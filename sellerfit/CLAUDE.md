# CLAUDE.md — SellerFit 프로젝트 작업 지침

> 이 파일은 Claude Code가 프로젝트를 열 때 자동으로 읽는 컨텍스트 파일입니다.
> 작업 시작 전 반드시 이 문서 전체와 `docs/HANDOVER.md`를 먼저 읽으세요.

---

## 프로젝트 한 줄 요약

**도매꾹 상품번호를 입력하면 → AI가 가격/카테고리/이미지를 처리해서 → 쿠팡에 자동 등록하는 데스크톱 프로그램.**

개발자: 김도완 (한량컴퍼니). 한국 시장 자동화 봇 전문.

---

## 🚨 절대 지켜야 할 개발 원칙 (도완님 8대 원칙)

1. **잘 돌아가는 코드는 절대 건드리지 마라.** 요청받은 특정 함수/줄만 수정. 임의 리팩토링 금지.
2. **수정 전 영향도 파악.** 공통 모듈 수정 시 다른 기능 안 깨지게 조건문/파라미터로 격리.
3. **묻지마 덮어쓰기 금지.** 전체 파일 재생성 X. 변경 부분만 명확히.
4. **콘텐츠 도메인 규칙:** 의사/병원/전문의 단어·이미지 금지. 블로그 태그 정확히 10개. 팩트 기반.
5. **수정 후 보고 양식 필수:**
   ```
   수정된 파일명 / 수정한 함수 / 수정 내용 요약 /
   다른 기능 영향 없는 이유 / EXE 빌드 영향 여부 / 잔존 에러 리스크
   ```
6. **EXE 빌드 환경 분리.** `sys.frozen` 가드 필수. BASE_DIR 분기. 한글 경로 대응(encoding='utf-8').
7. **파일당 500줄 상한.** 넘으면 기능별 분리 제안 후 승인받고 진행.
8. **셀렉터/URL/엔드포인트 하드코딩 금지.** config나 파일 상단 변수로. 매직넘버 금지.

**추가 규칙:**
- 코드 수정은 반드시 **사용자 확인 후** 진행. 먼저 실행하지 말 것.
- 수정 전 before/after 비교 제시 → 승인 → 진행.
- 한 번에 하나씩 수정, 완료 확인 후 다음.
- `.env`, `config.json`, `license_generator.py` 등 민감파일 빌드 포함 금지.
- 모든 API 키/아이디/비번 기본값은 빈 문자열("").
- 답변은 핵심만. 과도한 설명 자제. 버튼 팝업(ask_user_input) 쓰지 말고 텍스트로 질문.

---

## 현재 개발 상태 (Slice 1 — 단일상품 등록)

### ✅ 완성된 것
- 도매꾹 API 상품 조회 (`domeggook_client.py`)
- 쿠팡 WING API 클라이언트 + HMAC 인증 (`coupang_wing_client.py`)
- 가격 계산 3모드: multiply/add_margin/min_margin (`pricing.py`)
- 카테고리 자동 추천 + 캐시 (`category_mapper.py`)
- 카테고리 필수옵션(attributes) 자동 채움 (`payload_builder.py`)
- 반품지/출고지 자동 조회 (`coupang_metadata_collector.py`)
- 단계별 JSON 스냅샷 (`data_snapshot.py`)
- CLI 진입점 (`main.py`)
- GUI — 조회/등록 2단계 + 가격조정 + 실시간로그 (`gui_app.py`, `pipeline_service.py`)

### ⚠️ 미검증 (실제 API 호출 안 해봄)
- 도완님이 아직 `.env`에 실제 키 넣고 돌려본 적 없음
- 쿠팡 실제 등록 성공 여부 미확인
- 도매꾹 실제 XML 응답 형식 (모의 데이터로만 테스트)

### ❌ 아직 없는 것 (다음 Slice)
- **대량 등록** (현재 1개씩만)
- AI 카피 생성 (Claude)
- 상세페이지 템플릿
- 옵션 다건 (색상/사이즈 여러 개)
- 라이선스/빌드(EXE)

---

## 기술 스택

- Python 3.10+ (도완님 환경 3.12, 3.13은 greenlet 이슈로 회피)
- requests, python-dotenv, customtkinter
- 도매꾹 Open API (EUC-KR 인코딩, 분당 180회/일 15000회 제한)
- 쿠팡 WING Open API (HMAC-SHA256, `X-Requested-By` 헤더 필수)
- 배포 예정: PyInstaller + Inno Setup

---

## 아키텍처 (데이터 흐름)

```
[GUI: gui_app.py]
   ↓ 사용자가 상품번호 입력 + [조회]
[pipeline_service.py: fetch_product()]
   ↓
   1. coupang_metadata_collector → 반품지/출고지 (24h 캐시)
   2. domeggook_client → 상품 조회 (XML 파싱)
   3. pricing → 가격 계산
   4. category_mapper → 카테고리 추천
   4b. coupang_wing_client.get_required_attributes → 필수옵션
   5. image_pipeline → 이미지 접근성
   6. payload_builder → 쿠팡 등록 JSON 조립 + 검증
   ↓ 화면에 결과 표시, 사용자가 [등록] 클릭
[pipeline_service.py: register_product()]
   ↓
   7. coupang_wing_client.create_product → 실제 등록
   8. (선택) request_approval → 승인요청
   ↓
[모든 단계 → data_snapshot이 snapshots/{상품번호}_{시각}/*.json 저장]
```

**핵심 설계 원칙:**
- CLI(`main.py`)와 GUI(`pipeline_service.py`)는 같은 엔진 모듈을 공유
- 엔진 모듈(domeggook/coupang/pricing 등)은 UI를 모름 (재사용 가능)
- 모든 단계 스냅샷 저장 → 디버깅·재시작 용이

---

## 파일별 역할 + 수정 시 주의

| 파일 | 역할 | 수정 주의 |
|---|---|---|
| `config.py` | 환경변수·설정 | 모든 설정의 출처. 신중히 |
| `logger.py` | 로깅 | 거의 수정 불필요 |
| `data_snapshot.py` | 단계별 JSON 저장 | 거의 수정 불필요 |
| `domeggook_client.py` | 도매꾹 API | XML 파싱 — 실제 응답 다르면 `_extract_images`, `_parse_xml` 튜닝 |
| `coupang_wing_client.py` | 쿠팡 API | HMAC 서명 건드리지 말 것. 엔드포인트는 `Endpoints` 클래스에 |
| `coupang_metadata_collector.py` | 반품지/출고지 | 24h 캐시 로직 |
| `category_mapper.py` | 카테고리 추천 | 영구 캐시. 정확도 낮으면 여기 |
| `pricing.py` | 가격 계산 | 3모드. 검증 완료. 안정적 |
| `image_pipeline.py` | 이미지 처리 | 쿠팡이 URL 거부 시 자체 호스팅 추가 필요 |
| `payload_builder.py` | **쿠팡 JSON 조립** | **507줄, 가장 복잡, 가장 자주 수정. 분리 후보** |
| `pipeline_service.py` | GUI용 서비스 | 조회/등록 분리. 대량등록 시 여기 확장 |
| `main.py` | CLI 진입점 | GUI와 흐름 동일하게 유지 |
| `gui_app.py` | GUI | CustomTkinter. 대량등록 UI 추가 예정 |

---

## 실행 방법

```bash
pip install -r requirements.txt
cp .env.example .env
# .env에 실제 키 입력 (아래 5개)

python main.py --config          # 설정 확인
python main.py 23828709 --dry-run  # 등록 없이 검증
python main.py 23828709          # 실제 등록 (임시저장)
python gui_app.py                # GUI 실행
```

### .env 필수 항목 (5개)
```
DOMEGGOOK_API_KEY=
COUPANG_WING_VENDOR_ID=     (A로 시작)
COUPANG_WING_ACCESS_KEY=
COUPANG_WING_SECRET_KEY=
COUPANG_WING_USER_ID=       (WING 로그인 아이디)
```

---

## 디버깅 가이드

문제 생기면 `snapshots/{상품번호}_{시각}/` 폴더의 JSON을 순서대로 확인:
- `01_coupang_metadata.json` — 반품지/출고지 정상?
- `02_domeggook_parsed.json` — 도매꾹 파싱 정상? (이미지/가격)
- `03_pricing.json` — 가격 계산 정상?
- `04_category.json` + `04b_required_attributes.json` — 카테고리/필수옵션?
- `05_images.json` — 이미지 접근 가능?
- `06_coupang_payload.json` — 쿠팡 전송 JSON (가장 중요)
- `07_coupang_response.json` — **쿠팡 에러 메시지 여기 있음**

---

## 다음 작업 우선순위 (상세는 docs/ROADMAP.md)

1. **실전 검증** — 도완님 실제 키로 1개 등록 성공시키기 (최우선)
2. **대량 등록** — 상품번호 여러 개 처리 (방식 미정: 직접입력 vs 검색 vs 엑셀)
3. AI 카피 + 템플릿
4. 옵션 다건
5. 빌드/배포

자세한 내용은 `docs/ROADMAP.md`와 `docs/HANDOVER.md` 참고.
