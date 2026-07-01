# 머무는순간 (StayClip)

> 감성 스테이·독채 펜션 전문 **숏폼 체험단**. 비주얼 되는 곳만, **공정위 100% 합법**으로, 숏폼(릴스·네이버 클립)으로 알립니다.

숙소 운영자와 여행·감성 라이프스타일 숏폼 크리에이터를 잇는 양면 시장 MVP입니다.
랜딩페이지에서 **숙소(광고주)** 와 **크리에이터** 신청을 받고, 운영자가 `/admin`에서 신청을 검토합니다.
(기획안의 린 MVP: 컨시어지 수동 운영 → 단계적 자동화)

## 핵심 흐름

```
홈(/) → 숙소 신청(/apply/host) · 크리에이터 신청(/apply/creator)
      → /api/applications 저장(applications 테이블)
      → 운영자 검토(/admin, 로그인 + ADMIN_EMAILS)
```

## 기술 스택

- **Next.js 16** (App Router) · **React 19** · **TypeScript** · **Tailwind CSS v4**
- **DB/Auth**: Supabase (`@supabase/ssr`, `@supabase/supabase-js`) + RLS

## 빠른 시작

```bash
npm install
cp .env.example .env.local   # 키는 비워둬도 됨(아래 참고)
npm run dev                  # http://localhost:3000
```

- **`/`** 마케팅 홈 · **`/apply/host`** 숙소 신청 · **`/apply/creator`** 크리에이터 신청
- **`/admin`** 운영자 신청 목록 (로그인 + `ADMIN_EMAILS` 등록 필요)

> 환경변수가 비어 있어도 사이트는 정상 빌드/구동됩니다. 이 경우 **신청 접수만 비활성화**되고(폼에 안내 표시), 홈·요금·합법 안내 등 정적 콘텐츠는 그대로 동작합니다.

## 환경변수 (`.env.local` / Vercel 대시보드)

| 변수 | 필수 | 설명 |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | 신청·로그인 | Supabase 프로젝트 URL (클라이언트 노출 안전) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 신청·로그인 | Supabase anon 키 (클라이언트 노출 안전) |
| `SUPABASE_SERVICE_ROLE_KEY` | 운영자 화면 | `/admin` 신청 목록 조회용(RLS 우회). **서버 전용, 절대 클라이언트 노출 금지** |
| `ADMIN_EMAILS` | 운영자 화면 | `/admin` 접근 허용 이메일(쉼표 구분). 비우면 로그인한 모든 계정 허용 |

## Supabase 설정

1. [supabase.com](https://supabase.com) 에서 프로젝트 생성
2. **SQL Editor** 에 `database/schema.sql` 전체를 붙여 실행 (profiles/applications + RLS + 가입 트리거)
3. **Project Settings → API** 에서 URL·anon·service_role 키를 복사해 `.env.local`(또는 Vercel)에 입력
4. 운영자 계정으로 `/signup` 가입 → 해당 이메일을 `ADMIN_EMAILS` 에 등록

### 보안 모델

- **공개 신청**: anon 권한으로 `applications` 에 insert 만 가능(RLS `with check`). 읽기 정책은 두지 않음.
- **운영자 조회**: 서버에서 `service_role` 키로만 조회(RLS 우회) + `ADMIN_EMAILS` 화이트리스트로 페이지 접근 제한.
- 신청 API에 IP 기준 rate limit + 필드 화이트리스트 정화(`lib/sanitize.ts`).
- 사용자 입력은 React 자동 이스케이프로 처리하며 `dangerouslySetInnerHTML` 미사용.

## Vercel 배포

Next.js는 Vercel에서 zero-config 입니다.

1. 이 저장소를 GitHub에 푸시
2. Vercel에서 **New Project → 이 repo import**
3. **Environment Variables** 에 위 표의 키 입력 (`.env.local` 은 배포 산출물에 포함되지 않음)
4. Deploy → 임시 도메인에서 동작 확인

## 디렉터리 구조

```
app/
  page.tsx                 마케팅 홈(머무는순간)
  apply/
    layout.tsx             신청 페이지 공통 셸(내비/푸터)
    host/page.tsx          숙소(광고주) 신청
    creator/page.tsx       크리에이터 신청
  admin/page.tsx           운영자 신청 목록(service_role + ADMIN_EMAILS)
  (auth)/login·signup      운영자 로그인/가입
  api/applications         신청 저장(검증·정화·rate limit)
  api/status               신청 접수 가능 여부
components/
  ApplicationForm.tsx      신청 폼(필드 정의 기반 렌더)
  site/                    Nav · Footer · Wordmark · icons
  auth.tsx · LogoutButton.tsx
lib/
  applications.ts          신청 필드 스키마(폼·서버 공용)
  brand.ts                 브랜드·패키지 상수
  db/                      supabase(브라우저/서버) + applications
  sanitize.ts · rateLimit.ts
database/schema.sql        profiles/applications + RLS
middleware.ts              Supabase 세션 갱신(미설정 시 no-op)
```

## 로드맵 (기획안 기준)

- **1단계(0~6개월)**: 한 지역·한 유형 집중, 베타 레퍼런스 확보, 컨시어지 수동 매칭
- **2단계(6~18개월)**: AI 소재팩 상품화, 인접 지역 복제, 반복작업 자동화
- **3단계(18개월+)**: 셀프서비스/성과 기반 과금, 카테고리 확장(글램핑·차박·로컬 체험)
