# DECISIONS.md

곰대리 멀티발행 MVP 빌드 중 내린 표준 선택 기록 (작업지시 규칙 2: 모호하면 가장 표준적인 선택 후 한 줄 기록하고 계속).
기준 문서: `gomdaeri_ultracode_build_spec_v1`.

| # | 결정 | 근거 |
|---|------|------|
| 1 | **스택: Prisma+Clerk 대신 Supabase(Postgres+Auth) 유지** | 스펙 §3은 스택을 "추천·교체 가능"으로 명시. 레포에 이미 Supabase가 설치·배선됨(미들웨어/서버 클라이언트/인증 페이지). Supabase=Postgres라 포인트 ACID 충족. §13 "잘 도는 코드 건드리지 않기". Clerk 전환은 외부 계정 필요 + 작동 코드 제거 = 불필요한 위험. |
| 2 | **기존 "PromptSite" 제품 코드 보존, 곰대리 멀티발행을 1차 제품으로** | 스펙 §1 "플랫폼 1층 + 제품 N개" 구조. 기존 PromptSite는 다른 제품이자 재사용 인프라의 출처. 라우트 충돌 없음(`/api/generations`·`/workspace` 신규). 홈(`app/page.tsx`)·레이아웃 브랜딩만 곰대리로 교체. |
| 3 | **AI 게이트웨이는 신규 작성(§8), 기존 provider-core는 호출 패턴만 재사용** | 기존 `withFallback`은 string만 반환 → §8은 `{text,usage,costUsd}` + 모델 티어링 + 원가계산 필요. Anthropic SDK의 `usage`(input/output tokens) 포착해 cost 계산. |
| 4 | **모델 ID: Haiku=`claude-haiku-4-5`, Sonnet=`claude-sonnet-4-6` (env override)** | 스펙 §8은 "Haiku/Sonnet" 티어만 지정, 정확 ID는 빌드 시 확정이라 명시. 2026 기준 최신 ID 사용, config로 외부화. |
| 5 | **워커 = 표준 단일 워커 프로세스 + 스토리지 추상화(Supabase / 인메모리)** | 스펙은 "DB 잡테이블 + 워커 프로세스" 요구. 키 없이도 §16 검증 가능하도록 인메모리 백엔드 + 인프로세스 kick 제공(기존 mock 모드 철학과 일관). 운영은 `npm run worker` 장기 프로세스(Railway 정신). |
| 6 | **잡 큐 = 별도 jobs 테이블 대신 `generations.status`를 큐로 사용** | MVP 단순화(스펙 §3 "DB 잡테이블 + 워커, MVP 단순"). 한 generation = 한 잡. 상태 머신: queued→processing→done/partial/failed. |
| 7 | **원자적 차감 = Postgres SECURITY DEFINER 함수(RPC) 1트랜잭션** | 스펙 §12 동시성: 행잠금/원자 업데이트로 이중차감·음수잔액 방지. `update ... set balance=balance-cost where balance>=cost` 가드 + ledger + usage_event 한 트랜잭션. |
| 8 | **체험 포인트 = 30P (가입 시 grant)** | 스펙 §10/§12 "예: 30P". |
| 9 | **포인트 상수 = SET 10 / BLOG_REGEN 5 / CHANNEL_REGEN 2 / CORE_REGEN 2** | 스펙 §7 config 상수 그대로. |
| 10 | **단가표 = Haiku $1/$5, Sonnet $3/$15 per MTok (config)** | 스펙 §8. |
| 11 | **미들웨어 → `proxy.ts`로 마이그레이션** | Next.js 16에서 Middleware→Proxy 리네임, `middleware.ts`는 `@deprecated`. AGENTS.md "deprecation 준수". |
| 12 | **상태 전달 = GET 폴링(2~3초)** | 스펙 §4/§10 MVP는 폴링(SSE는 후일). |
| 13 | **보관(retention) 컬럼은 plans에 두되 배치 삭제는 미구현** | 스펙 §5에서 "보관 배치"는 P2 OUT. 정책값만 컬럼으로 보유. |
| 14 | **스크래퍼 1순위 HTTP = `got` 대신 Node22 네이티브 fetch** | §9 의도는 "가벼운 fetch 우선". 네이티브 fetch가 바로 그 가벼운 fetch이며 ESM 번들 리스크 0·더 견고. cheerio 파싱 + Playwright fallback 구조는 그대로. 스택 교체 가능(§3). |
| 15 | **Playwright는 lazy import + graceful degrade** | 브라우저 바이너리 없는 환경에서도 빌드/실행되도록. 미설치 시 경고 로그 + 해당 URL 스킵("팩트 근거 없음"). serverExternalPackages로 번들 제외. |
