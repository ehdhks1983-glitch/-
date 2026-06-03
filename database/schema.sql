-- database/schema.sql  [신규]
-- PromptSite MVP 스키마: profiles / projects / leads + RLS.
-- Supabase SQL Editor 에 그대로 붙여 실행하세요. (재실행 안전하도록 IF NOT EXISTS 사용)

-- ───────────────────────── profiles ─────────────────────────
create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text,
  created_at  timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id);

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

-- ───────────────────────── projects ─────────────────────────
create table if not exists public.projects (
  id          uuid primary key default gen_random_uuid(),
  owner       uuid not null references auth.users (id) on delete cascade,
  slug        text not null unique,
  title       text not null default '',
  prompt      text not null default '',
  template    text not null default 'saas-launch',
  biz_info    jsonb not null default '{}'::jsonb,
  copy        jsonb not null default '{}'::jsonb,
  published   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists projects_owner_idx on public.projects (owner);
create index if not exists projects_slug_idx on public.projects (slug);

alter table public.projects enable row level security;

-- 소유자는 자기 프로젝트 전체 권한
drop policy if exists "projects_owner_all" on public.projects;
create policy "projects_owner_all" on public.projects
  for all using (auth.uid() = owner) with check (auth.uid() = owner);

-- 누구나(비로그인 포함) 게시된 프로젝트는 조회 가능(공개 페이지 서빙용)
drop policy if exists "projects_public_read" on public.projects;
create policy "projects_public_read" on public.projects
  for select using (published = true);

-- ───────────────────────── leads ─────────────────────────
create table if not exists public.leads (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references public.projects (id) on delete cascade,
  email       text not null,
  meta        jsonb,
  created_at  timestamptz not null default now()
);

create index if not exists leads_project_idx on public.leads (project_id);

alter table public.leads enable row level security;

-- 프로젝트 소유자만 신청자 목록 조회
drop policy if exists "leads_owner_select" on public.leads;
create policy "leads_owner_select" on public.leads
  for select using (
    exists (select 1 from public.projects p where p.id = leads.project_id and p.owner = auth.uid())
  );

-- 공개 페이지에서 신청 insert 가능(단, 게시된 프로젝트에 한함). select 와 분리된 정책.
drop policy if exists "leads_public_insert" on public.leads;
create policy "leads_public_insert" on public.leads
  for insert with check (
    exists (select 1 from public.projects p where p.id = leads.project_id and p.published = true)
  );
