# PromptSite

> 프롬프트 한 줄이면 랜딩페이지가 **딸깍** 완성. AI가 팔리는 카피와 디자인, 신청 폼까지 만들어 바로 게시합니다.

사용자가 사업/서비스를 한 줄로 적으면 → AI가 분석하고(부족하면 보완질문) → 전환 중심 카피를 생성해 → 어울리는 템플릿에 주입하고 → 공개 URL로 게시 → 방문자 이메일(리드)까지 수집합니다.

여기에 **워드프레스 자동 발행**(`/wordpress`)이 추가되었습니다: 내 워드프레스 블로그를 연결해 카테고리를 관리하고, 키워드만으로 AI 글을 만들어 즉시/예약/대량 자동 발행까지 합니다. → [자세히](#워드프레스-자동-발행)

## 핵심 파이프라인

```
프롬프트 → analyzePrompt → (clarifyQuestions) → generateCopy → selectTemplate → 미리보기 → 게시(s/[slug]) → 리드 수집
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
| `SUPABASE_SERVICE_ROLE_KEY` | 선택 | 서버 전용 관리자 작업용. **절대 클라이언트 노출 금지** |
| `OPENAI_TEXT_MODEL` 등 | 선택 | 모델 ID override (기본값은 `lib/ai/config.ts`) |

> 키가 전부 비어 있어도 앱은 정상 빌드/구동됩니다. 생성은 목 모드, 인증/저장/게시는 안내 메시지로 비활성화됩니다.

## Supabase 설정 (게시·리드 기능)

1. [supabase.com](https://supabase.com) 에서 프로젝트 생성
2. **SQL Editor** 에 `database/schema.sql` 전체를 붙여 실행 (profiles/projects/leads + RLS + 가입 트리거)
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
  dashboard/                   내 프로젝트 / [projectId]/leads 신청자
  wordpress/                   ★워드프레스 자동 발행(연결/카테고리/글쓰기/대량/현황)
  (auth)/login·signup
  api/generate · api/projects · api/leads
  api/wp/                      WP REST 프록시(test·categories·posts·generate)
components/templates/          SaasLaunch · Waitlist · Agency + TemplateRenderer
components/wp/                 WpNav · NotConnected
lib/ai/                        types·config·core + analyze/clarify/generate/select/render/generatePost
lib/wp/                        types·connection·guard(SSRF)·client(WP REST)·sanitizeHtml·clientStore
lib/db/                        supabase(브라우저/서버) + projects/leads
lib/sanitize.ts · lib/rateLimit.ts · lib/seo/meta.ts
database/schema.sql            테이블 + RLS
middleware.ts                  Supabase 세션 갱신(미설정 시 no-op)
```

## 워드프레스 자동 발행

`/wordpress` 에서 내 워드프레스 사이트를 연결하면:

| 메뉴 | 기능 |
|---|---|
| 연결 설정 | 사이트 주소 + 아이디 + **응용 프로그램 비밀번호**로 연결 테스트·저장 |
| 카테고리 관리 | 트리(글 개수 포함) 보기, 추가/수정/삭제, 슬러그·설명·상위 카테고리 |
| AI 글쓰기 | 키워드 → AI 초안(제목·본문·요약·태그) → 검토·수정 → 즉시/임시/예약 발행 |
| 대량 자동화 | 키워드 여러 개(최대 20)를 매일/2·3일/매주 간격으로 자동 생성·예약 등록 |
| 발행 현황 | 발행/예약/임시글 필터, 즉시 발행·삭제, WP 관리자 편집 링크 |

### 연결 준비 (1분)

1. 워드프레스 관리자 → **사용자 → 프로필** → 아래쪽 **응용 프로그램 비밀번호**
2. 이름(예: `promptsite`) 입력 후 **추가** → 표시되는 24자리 비밀번호 복사
3. `/wordpress` 연결 설정에 사이트 주소(https), 아이디, 복사한 비밀번호 입력

> 워드프레스 5.6+ 기본 기능입니다. 사이트가 **https** 여야 하고, 보안 플러그인이 REST API나
> 응용 프로그램 비밀번호를 차단하면 해제가 필요합니다. 연결 해제는 같은 화면에서 비밀번호
> **철회**로 즉시 가능합니다.

### 동작 방식·보안

- **무상태 프록시**: 접속 정보는 **브라우저 localStorage에만** 저장됩니다. 서버·DB에는 저장하지
  않고, 요청마다 `x-wp-connection` 헤더로 받아 WP REST API(`/wp-json/wp/v2/*`)로 중계만 합니다.
- **SSRF 가드**(`lib/wp/guard.ts`): https 강제, 내부망 도메인/사설·예약 IP 차단(리터럴 + DNS 조회
  검사), 리다이렉트 미추적. (DNS 리바인딩까지 완전 차단하지는 않는 1차 방어입니다)
- **본문 HTML 정화**(`lib/wp/sanitizeHtml.ts`): AI 본문은 허용 태그(h2·h3·p·ul·ol·li·strong·em 등)만
  **속성 없이 재조립**합니다. 미리보기 렌더와 WP 전송 모두 이 결과만 사용하므로 스크립트/이벤트
  속성이 끼어들 수 없습니다.
- **비용 방어**: 글 생성 분당 12회, 프록시 분당 90회, 연결 테스트 분당 20회(IP 기준).
- AI 키가 없으면 글 생성은 **목 모드**(예시 초안)로 동작 — 발행 파이프라인은 그대로 테스트 가능.

### 알아둘 점

- **예약 발행은 워드프레스(WP-Cron)가 처리**합니다. 방문이 거의 없는 사이트는 예약 시각이 지나도
  다음 방문 때 발행되니, 정시가 중요하면 서버 크론으로 `wp-cron.php`를 걸어두세요.
- 대량 자동화 실행 중에는 탭을 닫지 마세요(등록이 끝나면 닫아도 예약은 유지됩니다).
- 카테고리 삭제 시 소속 글은 WP 기본 카테고리로 이동합니다(글은 삭제되지 않음).

## 모델 폴백 체인 (`lib/ai/config.ts`)

- **copy**(핵심 IP, 품질 우선): Claude Opus → Claude Sonnet → Gemini Pro → OpenAI
- **analyze/clarify**(비용·속도 우선): Claude Sonnet → Gemini Flash → OpenAI
- 상위 모델 실패/타임아웃 시 자동으로 하위로 폴백. 키 없는 프로바이더는 건너뜀.
- 모델 ID·타임아웃·재시도는 전부 `config.ts`(또는 env)에서만 관리(하드코딩 금지).

## 보안

- AI 생성 텍스트는 React 자동 이스케이프 + `sanitizeCopy` 이중 방어. `dangerouslySetInnerHTML` 미사용.
- Supabase RLS: 프로젝트/리드는 소유자만, 게시물은 공개 read, 리드는 게시된 프로젝트에만 insert.
- 생성/저장/신청 엔드포인트에 IP 기준 rate limit (토큰 비용·스팸 방지).
- `service_role` 키는 서버 전용. `.env*` 는 커밋 금지(`.env.example` 만 예외).

## 다음 단계 (로드맵)

- **2차**: 이미지 생성, 다국어, 광고 픽셀, GEO 고급(llms.txt/스키마), 프로젝트 재편집
- **3차**: 결제(Toss/Lemon Squeezy), 커스텀 도메인
- **WP 자동화**: 대표 이미지(미디어 업로드), 여러 사이트 저장, 접속정보 서버 보관(암호화+RLS),
  글 재생성·리라이팅, 발행 결과 리포트
```
