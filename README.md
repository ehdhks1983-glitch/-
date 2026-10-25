# PromptSite

> 프롬프트 한 줄이면 랜딩페이지가 **딸깍** 완성. AI가 팔리는 카피와 디자인, 신청 폼까지 만들어 바로 게시합니다.

사용자가 사업/서비스를 한 줄로 적으면 → AI가 분석하고(부족하면 보완질문) → 전환 중심 카피를 생성해 → 어울리는 템플릿에 주입하고 → 공개 URL로 게시 → 방문자 이메일(리드)까지 수집합니다.

## 핵심 파이프라인

```
프롬프트 → analyzePrompt → (clarifyQuestions) → generateCopy(+업종 금칙어 검사·1회 자동 재작성) → selectTemplate
        → 미리보기 → 게시 전 확인(승인) → 게시(s/[slug], AI 생성 표시) → 리드 수집
```

## 기술 스택

- **Next.js 16** (App Router) · **React 19** · **TypeScript** · **Tailwind CSS v4**
- **AI**: `@anthropic-ai/sdk`, `@google/genai`, `openai` — 3사 폴백 체인 (`lib/ai/config.ts`)
- **DB/Auth**: Supabase (`@supabase/ssr`, `@supabase/supabase-js`) + RLS

## 빠른 시작

```bash
npm install
cp .env.example .env.local   # 키는 비워둬도 됨(아래 "목 모드" 참고)
npm run dev                  # http://localhost:3000
```

- **`/`** 마케팅 홈 → **`/project/new`** 에서 바로 생성 체험
- 파이프라인만 콘솔로 확인: `npm run test:ai "온라인 PT 코칭 랜딩, 30대 직장인, 무료 상담"`
- 업종 감지·금칙어·게시 승인·규제 피드 검증: `npm run test:compliance` (키·DB 불필요)
- 유입 경로 판별·성과 집계 검증: `npm run test:analytics` (키·DB 불필요)
- MCP(AI 비서 연동) 프로토콜 검증: `npm run test:mcp` (키·DB 불필요)

### 목(mock) 모드

AI 프로바이더 키가 **하나도 없으면** `lib/ai/core.ts` 가 결정적 목 응답을 돌려줍니다.
→ 키 없이도 생성→미리보기 흐름 전체를 개발/테스트할 수 있습니다. 강제로 켜려면 `PROMPTSITE_MOCK=1`.

## 환경변수 (`.env.local` / Vercel 대시보드)

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 권장 | Claude(카피 품질 주력). 없으면 하위 프로바이더로 폴백 |
| `GEMINI_API_KEY` | 선택 | Gemini 폴백 |
| `OPENAI_API_KEY` | 선택 | OpenAI 폴백(최후순위) |
| `NEXT_PUBLIC_SUPABASE_URL` | 게시 기능 | Supabase 프로젝트 URL (클라이언트 노출 안전) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 게시 기능 | Supabase anon 키 (클라이언트 노출 안전) |
| `SUPABASE_SERVICE_ROLE_KEY` | 선택 | 서버 전용 관리자 작업용(AI 비서 연동의 계정 도구에 필요). **절대 클라이언트 노출 금지** |
| `OPENAI_TEXT_MODEL` 등 | 선택 | 모델 ID override (기본값은 `lib/ai/config.ts`) |

> 키가 전부 비어 있어도 앱은 정상 빌드/구동됩니다. 생성은 목 모드, 인증/저장/게시는 안내 메시지로 비활성화됩니다.

## Supabase 설정 (게시·리드 기능)

1. [supabase.com](https://supabase.com) 에서 프로젝트 생성
2. **SQL Editor** 에 `database/schema.sql` 전체를 붙여 실행 (profiles/projects/leads + RLS + 가입 트리거)
   - 이미 배포한 DB도 다시 실행하면 됩니다(재실행 안전). 게시 승인 기록용 `projects.compliance` 컬럼, `compliance_logs`(승인 감사 로그),
     `page_stats`(방문 집계)와 `record_page_view()` 함수, `api_tokens`(AI 비서 연동 토큰)가 추가됩니다.
3. **Project Settings → API** 에서 URL·anon 키를 복사해 `.env.local`(또는 Vercel)에 입력
4. Auth → 이메일 가입을 사용하면 됩니다(기본). 확인 메일 설정은 Supabase Auth 설정에서 조정

## Vercel 배포

Next.js는 Vercel에서 zero-config 입니다.

1. 이 저장소를 GitHub에 푸시
2. Vercel에서 **New Project → 이 repo import**
3. **Environment Variables** 에 위 표의 키 입력 (`.env.local` 은 배포 산출물에 포함되지 않음 — `.gitignore` 처리)
4. Deploy → 임시 도메인에서 동작 확인

> 생성 엔드포인트(`/api/generate`)는 AI 호출 때문에 함수 타임아웃이 필요합니다. 라우트에 `maxDuration = 60` 을 설정해 두었습니다(Vercel 플랜의 함수 실행시간 한도 확인 권장).

## 디렉터리 구조

```
app/
  page.tsx                     마케팅 홈
  project/[id]/page.tsx        ★생성·보완질문·미리보기·게시
  project/[id]/preview         전체화면 미리보기
  s/[slug]/page.tsx            ★공개 게시 페이지(멀티테넌트) + 신청 폼
  dashboard/                   내 프로젝트 / [projectId]/leads 신청자 / [projectId]/stats 성과
  (auth)/login·signup
  api/generate · api/projects · api/leads
components/templates/          SaasLaunch · Waitlist · Agency + TemplateRenderer
lib/ai/                        types·config·core + analyze/clarify/generate/select/render
lib/compliance/                업종 프리셋·금칙어 규칙·검사·게시 승인·AI 고지 문구
components/PublishReview.tsx   게시 전 확인 창 · ComplianceFooter.tsx 공개 페이지 고지 띠
lib/db/                        supabase(브라우저/서버) + projects/leads
lib/sanitize.ts · lib/rateLimit.ts · lib/seo/meta.ts
database/schema.sql            테이블 + RLS
middleware.ts                  Supabase 세션 갱신(미설정 시 no-op)
```

## 모델 폴백 체인 (`lib/ai/config.ts`)

- **copy**(핵심 IP, 품질 우선): Claude Opus → Claude Sonnet → Gemini Pro → OpenAI
- **analyze/clarify**(비용·속도 우선): Claude Sonnet → Gemini Flash → OpenAI
- 상위 모델 실패/타임아웃 시 자동으로 하위로 폴백. 키 없는 프로바이더는 건너뜀.
- 모델 ID·타임아웃·재시도는 전부 `config.ts`(또는 env)에서만 관리(하드코딩 금지).

## 광고 규정·AI 고지 (`lib/compliance/`)

2026년 시행 규정(AI 기본법, 공정위 추천·보증 지침·실증고시, 식품표시광고법·의료법·학원법·화장품법)에 맞춰
생성 → 게시 사이에 컴플라이언스 층을 둡니다. 조사 근거는 `reports/곰대리 자동화 2026 기능 업데이트.md` 참고(법률 자문 아님).

- **업종 프리셋 7종**(일반·식당카페·미용·학원·병원·건강기능식품·화장품): 키워드로 자동 추정, 미리보기에서 변경 가능.
  업종 규칙이 생성 프롬프트에 들어갑니다.
- **금칙어 검사**: `block`(게시 불가 — 질병 효능, 의사·약사 추천, 의료 안전 단정, 합격 보장 등)과 `warn`(확인 후 게시 — 최상급·보장·손님 체험담 등).
  생성 직후 block 이 나오면 문제 표현을 피드백으로 주고 1회 다시 씁니다.
- **게시 전 확인**: 검사 결과, 업종 필수 표시(학원 등록번호·교습비, 건기식 자율심의 번호), AI 표시 설정, 사장님 승인 체크.
  서버(`/api/projects`)가 카피를 다시 검사해 통과할 때만 저장하고 승인 기록(시각·사용자·고지 버전·남은 경고)을 `projects.compliance` 에 남깁니다.
- **승인 감사 로그**: 승인할 때마다 기록 + 그때의 카피·템플릿 스냅샷을 `compliance_logs` 에 쌓습니다(append-only, 프로젝트 삭제 후에도 보존).
- **신청 폼 개인정보 동의**: 수집 항목·목적·보유기간·거부권을 고지하고 필수 동의를 받습니다. 서버도 동의를 확인하고 동의 버전·시각을 `leads.meta` 에 남깁니다.
- **AI 사전고지·결과물 표시**: 생성 화면·회원가입(동의 기록)에 사전고지, 공개 페이지 하단에 ‘생성형 AI로 작성’ 표시(기본 켜짐, 끄려면 확인 필요).
- 문구를 바꾸면 `lib/compliance/notice.ts` 의 `AI_NOTICE_VERSION` 을 올리세요.
- **규제 피드** `GET /api/compliance/rules`: 업종 프리셋·금칙어 규칙(정규식 source+flags)·AI 고지 문구를 JSON 으로 공개합니다.
  블로그·카페·쇼츠·스레드 등 다른 곰대리 프로그램이 같은 규칙을 받아 쓰는 단일 출처입니다. `version` 을 저장해 두고
  `If-None-Match: "<version>"` 으로 요청하면 변경이 없을 때 304 를 받습니다. 규칙을 바꾸면 `RULES_VERSION` 을 올리세요.

## 성과 리포트 (`/dashboard/[projectId]/stats`)

- '만든 페이지 수'가 아니라 **방문 → 신청 전환**을 보여 줍니다: 최근 30일 방문·신청·전환율, 일별 방문(14일), 유입 경로별 방문·신청·전환율.
- 방문은 공개 페이지에서 탭당 1회만 세고(`ViewTracker` → `/api/views`), 봇·링크 미리보기는 제외합니다.
  IP·UA 원문은 저장하지 않고 일·경로 단위 카운터만 올립니다(`record_page_view()` — 게시된 페이지만 반영).
- 유입 경로는 `utm_source` → 인앱 브라우저(카카오톡·인스타) → referrer 순으로 판별합니다. 성과 화면의
  **채널별 공유 링크**(utm 자동 부착)를 쓰면 경로가 정확해집니다. 신청에도 같은 경로가 기록돼 경로별 전환율이 나옵니다.

## AI 비서 연동 (MCP, `/api/mcp`)

ChatGPT·Claude 등 MCP 를 지원하는 AI 비서가 연결해 쓰는 도구 서버입니다(Streamable HTTP, stateless JSON-RPC).

| 도구 | 토큰 | 하는 일 |
|---|---|---|
| `check_ad_copy` | 불필요 | 자유 문구를 업종 광고 규정으로 검사(block/warn) |
| `get_compliance_rules` | 불필요 | 규제 피드와 같은 규칙·업종 프리셋 |
| `list_pages` | 필요 | 내 페이지 목록·게시 상태·최근 7일 방문/신청·주소 |
| `get_page_stats` | 필요 | 페이지 하나의 7/30일 성과·유입 경로 |
| `create_draft_page` | 필요 | 설명 한 줄 → 문구 생성 → **비공개 초안** 저장(1시간 10개) |

- **게시는 하지 않습니다.** 초안은 사장님이 편집 화면에서 검사 결과를 보고 승인해야 공개됩니다(게시 전 승인 원칙 유지).
- 신청자 이메일 등 개인정보를 돌려주는 도구는 없습니다.
- 인증: 대시보드 → **AI 연동**에서 개인 액세스 토큰을 발급해 `Authorization: Bearer <토큰>` 헤더로 보냅니다.
  토큰은 SHA-256 해시만 저장하며(원문은 발급 시 1회 표시), 계정 도구는 서버의 `SUPABASE_SERVICE_ROLE_KEY` 가 필요합니다.
- Claude Code: `claude mcp add --transport http promptsite https://<도메인>/api/mcp --header "Authorization: Bearer <토큰>"`
- OAuth 기반 연결(ChatGPT 커넥터 등 헤더를 넣을 수 없는 앱)은 아직 지원하지 않습니다.

## 보안

- AI 생성 텍스트는 React 자동 이스케이프 + `sanitizeCopy` 이중 방어. `dangerouslySetInnerHTML` 미사용.
- Supabase RLS: 프로젝트/리드는 소유자만, 게시물은 공개 read, 리드는 게시된 프로젝트에만 insert.
- 생성/저장/신청 엔드포인트에 IP 기준 rate limit (토큰 비용·스팸 방지).
- `service_role` 키는 서버 전용. `.env*` 는 커밋 금지(`.env.example` 만 예외).

## 다음 단계 (로드맵)

- **2차**: 이미지 생성, 다국어, 광고 픽셀, GEO 고급(llms.txt/스키마), 프로젝트 재편집
- **3차**: 결제(Toss/Lemon Squeezy), 커스텀 도메인
```
