# Claude Code에서 작업 시작하기

> 이 프로젝트를 Claude Code(클로드 코드)에서 이어서 개발하는 방법.

---

## 1. 프로젝트 열기

```bash
# 백업 ZIP 압축 해제 후
cd sellerfit_slice1

# Claude Code 실행
claude
```

Claude Code는 자동으로 `CLAUDE.md`를 읽습니다. 그 안에 프로젝트 규칙과 현재 상태가 다 있습니다.

---

## 2. 작업 시작 시 Claude에게 줄 첫 지시 (복붙용)

```
이 프로젝트는 SellerFit (도매꾹→쿠팡 자동등록 프로그램)이야.
먼저 CLAUDE.md, docs/HANDOVER.md, docs/ROADMAP.md를 읽고
현재 상태를 파악해줘. 그 다음 내가 작업 지시할게.

작업 원칙:
- 잘 돌아가는 코드는 건드리지 말 것
- 수정 전 반드시 나한테 확인받을 것
- 수정 후 보고 양식 지킬 것 (CLAUDE.md 참고)
- 핵심만 간결하게
```

---

## 3. 문서 읽는 순서 (Claude/사람 공통)

1. **`CLAUDE.md`** — 프로젝트 규칙 + 현재 상태 (가장 먼저)
2. **`docs/HANDOVER.md`** — 배경, 의사결정 히스토리, 삽질 방지
3. **`docs/ROADMAP.md`** — 완료분 + 향후 계획
4. **`docs/ARCHITECTURE.md`** — 코드 구조 (수정 작업 전)
5. **`README.md`** — 사용법

---

## 4. 자주 쓰는 작업별 시작 지시 예시

### 실전 검증 (최우선)
```
.env에 실제 API 키를 넣었어. 
python main.py [상품번호] --dry-run 을 실행하고
snapshots 폴더의 06_coupang_payload.json을 같이 보면서
실제 쿠팡 등록 가능한 상태인지 점검해줘.
```

### 대량 등록 개발
```
docs/ROADMAP.md의 Slice 2 (대량등록)를 시작하려고 해.
나는 [A: 직접입력 / B: 검색 / C: 엑셀] 방식으로 하고 싶어.
먼저 설계를 보여주고 내 승인을 받은 뒤 구현해줘.
```

### 버그 수정
```
[증상 설명]
snapshots/.../07_coupang_response.json에 이런 에러가 있어:
[에러 내용 붙여넣기]
원인 분석하고 수정 방안을 먼저 제시해줘. 바로 고치지 말고.
```

---

## 5. Claude Code 작업 시 주의

- Claude Code는 파일을 **직접 수정**할 수 있음 → 수정 전 확인 습관 중요
- 큰 변경 전 git commit 먼저 (`.gitignore` 이미 설정됨)
- `.env`는 절대 커밋 안 됨 (gitignore 처리됨)
- 수정 후 반드시 `python main.py --config`로 안 깨졌나 확인

---

## 6. 환경 셋업 (최초 1회)

```bash
pip install -r requirements.txt
cp .env.example .env
# .env 편집 — 실제 키 5개 입력
python main.py --config   # 설정 확인
```

### .env 필수 5개
```
DOMEGGOOK_API_KEY=
COUPANG_WING_VENDOR_ID=
COUPANG_WING_ACCESS_KEY=
COUPANG_WING_SECRET_KEY=
COUPANG_WING_USER_ID=
```
