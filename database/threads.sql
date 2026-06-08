-- database/threads.sql  [신규]
-- Threads 자동발행 기능 스키마: threads_accounts / threads_posts + RLS.
-- Supabase SQL Editor 에 그대로 붙여 실행하세요. (재실행 안전: IF NOT EXISTS / drop policy if exists)
-- 기존 schema.sql(profiles/projects/leads) 과 독립적으로 추가됩니다.
--
-- ⚠️ 토큰 보안: access_token 은 장기(약 60일) 토큰입니다.
--    - RLS 로 소유자만 접근. anon/타인은 절대 조회 불가.
--    - 클라이언트(브라우저)에는 절대 내려보내지 않음(앱 코드가 토큰 컬럼을 select 하지 않음).
--    - 서버 발행/크론만 토큰을 읽음(소유자 세션 또는 service_role).
--    - 더 강한 보호가 필요하면 운영 단계에서 pgsodium/Vault 로 컬럼 암호화를 권장.

-- ───────────────────────── threads_accounts ─────────────────────────
-- 사용자가 OAuth 로 연결한 Threads 계정(+장기 토큰). MVP: 사용자당 1계정(owner unique).
create table if not exists public.threads_accounts (
  id               uuid primary key default gen_random_uuid(),
  owner            uuid not null references auth.users (id) on delete cascade,
  threads_user_id  text not null,
  username         text not null default '',
  access_token     text not null,
  token_expires_at timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (owner)
);

create index if not exists threads_accounts_owner_idx on public.threads_accounts (owner);

alter table public.threads_accounts enable row level security;

-- 소유자만 자기 계정 행 전체 권한. 공개(anon) 정책 없음 → 토큰 노출 차단.
drop policy if exists "threads_accounts_owner_all" on public.threads_accounts;
create policy "threads_accounts_owner_all" on public.threads_accounts
  for all using (auth.uid() = owner) with check (auth.uid() = owner);

-- ───────────────────────── threads_posts ─────────────────────────
-- 발행 큐. 초안(draft) → 예약(scheduled) → 발행중(publishing) → 발행됨(published)/실패(failed)/취소(canceled).
create table if not exists public.threads_posts (
  id               uuid primary key default gen_random_uuid(),
  owner            uuid not null references auth.users (id) on delete cascade,
  account_id       uuid not null references public.threads_accounts (id) on delete cascade,
  text             text not null default '',
  media_type       text not null default 'TEXT',     -- TEXT | IMAGE
  image_url        text,
  status           text not null default 'draft',    -- draft|scheduled|publishing|published|failed|canceled
  scheduled_at     timestamptz,
  published_at     timestamptz,
  threads_media_id text,                              -- 발행 성공 시 Threads 게시물 id
  error            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists threads_posts_owner_idx on public.threads_posts (owner);
-- 크론이 "예약 + 발행시각 도래분"을 빠르게 스캔하기 위한 인덱스.
create index if not exists threads_posts_due_idx on public.threads_posts (status, scheduled_at);

alter table public.threads_posts enable row level security;

-- 소유자만 자기 게시물 전체 권한. (크론은 service_role 로 RLS 우회하여 발행.)
drop policy if exists "threads_posts_owner_all" on public.threads_posts;
create policy "threads_posts_owner_all" on public.threads_posts
  for all using (auth.uid() = owner) with check (auth.uid() = owner);
