# 곰대리 멀티발행 (Gomdaeri Multi-publish)

> 키워드와 참고자료에서 **핵심(코어)** 을 뽑아, **SEO 블로그 + 스레드·인스타·카페·쇼츠**를 채널별 native하게 한 번에 생성. 발행은 사용자가 **복붙**(자동 포스팅 X → 계정/ToS 리스크 0).

비기술 1인 마케터·창작자를 위한 웹 SaaS. **제로 셋업 · AI 내장**(사용자 키 입력 X). 빌드 기준 문서: `gomdaeri_ultracode_build_spec_v1`.

## 핵심 파이프라인

```
키워드 + 참고 URL → [워커] 스크래핑(§9) → 코어 추출(Haiku) → 병렬: 블로그(Sonnet) + 스레드·인스타·카페·쇼츠(Haiku)
                  → 저장 → 포인트 차감(10P) + usage_event(실측 AI 원가) → 폴링으로 결과 표시
```

- 무거운 생성은 **워커**에서(서버리스 타임아웃 회피 + UI 안 멈춤). UI는 `GET /api/generations/:id` 를 2~3초 폴링.
- 모든 AI 호출은 **게이트웨이**(`lib/gateway`)만 경유 — 모델 티어링·재시도·**토큰 원가계산**·캐싱 한 곳에서.

## 기술 스택

- **Next.js 16**(App Router, Turbopack) · React 19 · TypeScript · Tailwind v4
- **DB/Auth**: Supabase(Postgres + Auth, RLS). 포인트 정합성은 Postgres 원자 함수(`spend_points`).
- **AI**: `@anthropic-ai/sdk` — 모델 티어링(블로그=Sonnet, 그 외=Haiku). 게이트웨이 경유.
- **스크래핑**: 네이티브 fetch + `cheerio` → `playwright` 폴백(lazy)
- **잡 큐**: `generations.status` 를 큐로(별도 워커 프로세스) — `npm run worker`

> 스택은 스펙 §3 기준 "추천·교체 가능". Prisma+Clerk 대신 Supabase 채택 근거 등은 `DECISIONS.md` 참고.

## 빠른 시작 (키 없이도 동작)

```bash
npm install
cp .env.example .env.local     # 비워둬도 됨 → AI 목 모드 + 인메모리 저장/지갑
npm run dev                    # http://localhost:3000  → /workspace
```

키가 하나도 없으면: **AI=결정적 목(mock)**, **저장/인증/과금=인메모리 dev 모드**로 전체 흐름(생성→폴링→결과→복사→재생성→내 발행물)이 동작합니다. 강제 목: `GOMDAERI_MOCK=1`.

## 검증 (§16 체크리스트)

```bash
npm run test:gateway    # 텍스트+토큰+costUsd, 티어 매핑, 캐시
npm run test:scraper    # 네이버 모바일 경로 본문 추출 · 정규화 · 폴백
npm run test:pipeline   # 키워드+참고 → 코어 → 블로그+4채널 / facts 출처 · 태그 정확히 10개
npm run test:worker     # 큐 원자 점유 · 처리 루프
npm run test:billing    # 완료 −10 + tx + usage(ai_cost) / 실패 0 / 재생성 −2 / 잔액 가드
npm run lint && npm run build
```

## 운영 배포 (키 연결)

1. **Supabase 프로젝트** 생성 → SQL Editor에서 순서대로 실행:
   1. `database/schema.sql` (profiles 등)
   2. `database/multipublish_schema.sql` (멀티발행 9테이블 + RLS + 과금 함수 + 가입 트리거 + 시드)
2. `.env.local`(또는 호스트 대시보드)에 키 입력 → 표 참고.
3. **웹**(Next.js) + **워커**(`npm run worker`)를 분리해서 띄웁니다(Railway/Render 등 롱러닝 OK).

### 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 운영 | 게이트웨이(코어/블로그/채널). 없으면 목 모드 |
| `NEXT_PUBLIC_SUPABASE_URL` | 운영 | Supabase URL(클라이언트 노출 안전) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 운영 | anon 키(클라이언트 노출 안전) |
| `SUPABASE_SERVICE_ROLE_KEY` | 운영(워커) | 워커가 RLS 우회로 과금/저장. **서버 전용, 절대 클라이언트 금지** |
| `ANTHROPIC_MODEL_HAIKU` / `_SONNET` | 선택 | 모델 ID override |
| `PRICE_HAIKU_IN/OUT`, `PRICE_SONNET_IN/OUT` | 선택 | 단가(per MTok) override |
| `WORKER_POLL_MS`, `WORKER_CONCURRENCY` | 선택 | 워커 폴링/동시성 |

> **상용화 전 필요한 외부 계정/키**: Supabase 프로젝트(URL·anon·service_role) + Anthropic API 키. 이 둘만 연결하면 실제 모드로 전환됩니다.

## 디렉터리 (멀티발행)

```
app/workspace/                  ★새 발행(컨피규레이터+결과) · library 내 발행물 · library/[id] 재열람
app/api/generations/            POST 생성 · GET 목록 · [id] 폴링 · [id]/channels/[ch]/regenerate
app/api/wallet/                 잔액
lib/gateway/                    AI 게이트웨이(§8): 티어링·원가·재시도·캐싱·목
lib/pipeline/                   core + channels/{blog,threads,instagram,cafe,shorts} + prompts/sanitize
lib/scraper/                    config(사이트 규칙) + extract(cheerio) + index(fetch→playwright)
lib/store/                      generations 큐 추상화(memory / supabase)
lib/worker/                     process(파이프라인) + loop(runWorkerLoop) + kick
lib/billing/                    getBalance + chargePoints(원자) + devWallet(키리스)
lib/config/                     points(포인트 상수) · models(티어/단가)
database/multipublish_schema.sql  9테이블 + RLS + spend/grant/claim 함수
proxy.ts                        Next16 Proxy(구 middleware): 세션 갱신 + /workspace 보호
```

## 보안 (§14)

- AI 키는 **서버에만**(게이트웨이). 클라이언트엔 `NEXT_PUBLIC_*`(Supabase URL/anon)만 노출.
- 비밀값 전부 env, 기본 빈 문자열. `.env*` 커밋 금지(`.env.example`만).
- RLS 본인 스코프 + 과금은 원자 트랜잭션(이중차감·음수 잔액 방지).
- 생성 텍스트는 정화 후 표시(`dangerouslySetInnerHTML` 미사용).

---

> 참고: 이 저장소에는 별도 제품 **PromptSite**(랜딩페이지 빌더)의 코드도 보존되어 있습니다(스펙 §1 "플랫폼 + 제품 N개" 구조). 멀티발행과 인프라(Supabase·AI·rate limit·sanitize)를 공유하며 라우트는 분리되어 있습니다.
