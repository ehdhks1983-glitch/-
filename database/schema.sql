-- database/schema.sql
-- 머무는순간(StayClip) MVP 스키마: profiles / applications + RLS.
-- Supabase SQL Editor 에 그대로 붙여 실행하세요. (재실행 안전하도록 IF NOT EXISTS 사용)

-- ───────────────────────── profiles ─────────────────────────
-- 운영자(관리자) 로그인용. 신청 폼은 비로그인으로 동작한다.
create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text,
  created_at  timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);

-- 회원가입 시 프로필 자동 생성
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ───────────────────────── applications ─────────────────────────
-- 숙소(host)·크리에이터(creator) 신청을 한 테이블에 모은다.
create table if not exists public.applications (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null check (kind in ('host', 'creator')),
  name        text not null default '',
  email       text not null,
  phone       text,
  region      text,
  payload     jsonb not null default '{}'::jsonb,  -- 유형별 추가 필드
  status      text not null default 'new' check (status in ('new', 'reviewing', 'accepted', 'rejected')),
  created_at  timestamptz not null default now()
);

create index if not exists applications_kind_idx on public.applications (kind);
create index if not exists applications_created_idx on public.applications (created_at desc);

alter table public.applications enable row level security;

-- 공개 신청: 누구나(비로그인 포함) host/creator 신청을 insert 할 수 있다.
drop policy if exists "applications_public_insert" on public.applications;
create policy "applications_public_insert" on public.applications
  for insert with check (kind in ('host', 'creator'));

-- SELECT 정책은 일부러 두지 않는다 → anon/authenticated 는 신청 목록을 읽을 수 없다.
-- 운영자 조회(/admin)는 서버에서 service_role 키로만 수행한다(RLS 우회).
-- 즉 SUPABASE_SERVICE_ROLE_KEY + ADMIN_EMAILS 환경변수가 있어야 관리자 화면이 동작.
