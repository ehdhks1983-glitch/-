# 센텀하이 통합 라이선스 허브 (Centumhi License Hub)

센텀라이터·센텀토크·센텀커넥트·센텀모션·센텀브레인 등 모든 봇 제품의 7일/30일/무제한
라이선스 키를 **한 곳에서 통합 발급·검증·관리**하는 시스템.

- 도완(관리자)이 웹 대시보드 한 곳에서 모든 제품 키를 발급
- 각 봇 클라이언트는 중앙 검증 API 1개에만 요청 (HWID 바인딩 + HMAC 서명)
- 관리자/스탭 권한 분리, 만료 임박·HWID 충돌 자동 처리

## 모노레포 구조

```
centumhi-license-hub/
├── backend/     # FastAPI + SQLAlchemy 2.0 + SQLite/PostgreSQL  ← Phase 1 (완료)
├── frontend/    # Next.js 14 (App Router) + Tailwind + shadcn/ui ← Phase 2 (예정)
└── docs/        # 통합 가이드 / 배포 문서
```

## 진행 현황

| Phase | 내용 | 상태 |
|---|---|---|
| **1** | 백엔드 코어 (모델·인증·제품/라이선스/검증 API·스케줄러·테스트) | ✅ 완료 (`pytest` 31 통과) |
| 2 | 프론트엔드 (로그인·대시보드·키 발급/목록·활성화 현황) | ⬜ 예정 |
| 3 | 만료 알림·카톡 연동·통계/감사 로그 뷰 | ⬜ 예정 |
| 4 | `centumhi-license-client` 패키지 + 기존 봇 통합 PoC | ⬜ 예정 |
| 5 | Railway/Vercel 배포 + 도메인·백업 | ⬜ 예정 |

## 백엔드 빠른 시작

```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env          # JWT_SECRET_KEY, SEED_ADMIN_* 값 채우기
alembic upgrade head
python -m app.scripts.seed_admin

uvicorn app.main:app --reload # http://localhost:8000/docs
pytest                        # 테스트
```

봇 클라이언트 통합(검증 API, HMAC 서명)은 [`docs/API.md`](docs/API.md) 참고.

## 설계 메모

- 모든 timestamp는 **UTC 저장**, 응답은 ISO8601(`...Z`). 프론트에서 KST 변환.
- 라이선스 키 원본은 DB에 저장하지 않음 → **SHA-256 해시 + prefix(12자)** 만 저장, 발급 응답에서 1회만 노출.
- 봇 검증 엔드포인트는 **제품별 시크릿 기반 HMAC-SHA256** + timestamp 재생공격 방지.
- 통일 에러 스키마: `{ "error_code", "message", "detail?" }`.
