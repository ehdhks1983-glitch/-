# 배포 가이드

- **백엔드** → Railway (Dockerfile 빌드) · 도메인 `api.license.centumhi.co.kr`
- **프론트엔드** → Vercel · 도메인 `license.centumhi.co.kr`

---

## 1. 백엔드 (Railway)

`backend/Dockerfile` 과 `backend/railway.json` 이 준비되어 있습니다.

1. Railway에서 새 프로젝트 → GitHub 저장소 연결.
2. 서비스 **Root Directory** 를 `backend` 로 지정 (Dockerfile 자동 감지).
3. 환경변수 설정:

| 변수 | 예시 / 설명 |
|---|---|
| `JWT_SECRET_KEY` | 길고 랜덤한 값 (`openssl rand -hex 32`) |
| `DATABASE_URL` | `sqlite:////data/license_hub.db` (볼륨) 또는 `postgresql+psycopg://...` |
| `CORS_ORIGINS` | `https://license.centumhi.co.kr` |
| `ENVIRONMENT` | `prod` |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` / `SEED_ADMIN_NAME` | 최초 관리자 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |
| `VERIFY_TIMESTAMP_TOLERANCE_SEC` | `300` |
| `SCHEDULER_ENABLED` | `true` |
| `EXPIRY_NOTIFY_DAYS` | `3` |

4. 배포되면 컨테이너가 시작 시 `alembic upgrade head` 로 스키마를 만듭니다.
5. **최초 관리자 시드** — Railway 셸에서 1회 실행:
   ```bash
   python -m app.scripts.seed_admin
   ```
6. 커스텀 도메인 `api.license.centumhi.co.kr` 연결.

### SQLite vs PostgreSQL
- **SQLite**: 영구 볼륨을 `/data` 에 마운트하고 `DATABASE_URL=sqlite:////data/license_hub.db`.
  일일 백업은 볼륨 스냅샷 또는 cron으로 파일 복사.
- **PostgreSQL** (권장, 규모 확장 시): 의존성 추가 `pip install ".[pg]"`,
  `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/licensehub`. Alembic이 동일하게 마이그레이션.

---

## 2. 프론트엔드 (Vercel)

1. Vercel에서 저장소 import → **Root Directory** 를 `frontend` 로 지정 (Next.js 자동 감지).
2. 환경변수:

| 변수 | 값 |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://api.license.centumhi.co.kr/api` |

3. 배포 후 커스텀 도메인 `license.centumhi.co.kr` 연결.
4. 백엔드 `CORS_ORIGINS` 에 이 도메인이 포함되어 있는지 확인.

---

## 3. 봇 클라이언트

각 봇은 `centumhi-license-client` 를 설치하고 제품 시크릿/서버 URL을 환경변수로 받습니다.
[`CLIENT_INTEGRATION.md`](CLIENT_INTEGRATION.md) 참고.

---

## 4. 운영 체크리스트
- [ ] `JWT_SECRET_KEY` 는 절대 커밋하지 않음 (`.env` 는 gitignore됨).
- [ ] HTTPS 강제 (Railway/Vercel 기본 제공).
- [ ] 시드 관리자 비밀번호를 강력하게 설정.
- [ ] DB 백업 자동화 (SQLite 일일 → 추후 PG 관리형 백업).
- [ ] 제품 시크릿은 대시보드에서만 확인, 봇 환경변수로만 보관.
