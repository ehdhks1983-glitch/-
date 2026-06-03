# Centumhi License Hub — Backend

통합 라이선스 발급·검증 API (FastAPI + SQLAlchemy 2.0 + SQLite/PostgreSQL).

## 빠른 시작

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env          # 값 채우기 (특히 JWT_SECRET_KEY, SEED_ADMIN_*)

alembic upgrade head          # DB 스키마 생성
python -m app.scripts.seed_admin   # 관리자 계정 시드

uvicorn app.main:app --reload      # http://localhost:8000  (docs: /docs)
```

## 테스트

```bash
pytest
```

## 구조

| 경로 | 설명 |
|---|---|
| `app/main.py` | FastAPI 엔트리포인트, 에러 핸들러, CORS, 스케줄러 lifespan |
| `app/config.py` | 환경변수 설정 (pydantic-settings) |
| `app/database.py` | SQLAlchemy 엔진/세션 |
| `app/models/` | ORM 모델 (User, Product, License, Activation, AuditLog) |
| `app/schemas/` | Pydantic 요청/응답 스키마 |
| `app/core/` | 보안(JWT/bcrypt), 라이선스 키 생성, HMAC 검증, 에러 |
| `app/api/` | 라우터 (auth, products, licenses, verify, stats) |
| `app/services/` | 라이선스 서비스, 알림(stub), 스케줄러 |
| `app/scripts/` | 시드/운영 스크립트 |
| `alembic/` | DB 마이그레이션 |

자세한 API 통합 가이드는 `../docs/API.md` 참고.
