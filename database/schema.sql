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

-- 게시 전 승인 기록(업종·AI 표시·필수 표시 항목·승인 시각/사용자·사전고지 버전·남은 경고).
-- 기존 배포는 이 파일을 다시 실행하면 컬럼만 추가된다.
alter table public.projects add column if not exists compliance jsonb not null default '{}'::jsonb;

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
-- ⚠️ 한계: 이 정책은 게시물의 "모든 컬럼"(prompt·owner·biz_info 포함)을 anon 에 노출한다.
--    공개 페이지엔 copy/template/language 만 필요하므로, 운영 단계에서는 다음 중 하나를 권장:
--      (a) 공개 컬럼만 노출하는 VIEW(+ security_invoker), 또는
--      (b) anon 의 컬럼 SELECT 권한 제한(GRANT), 또는
--      (c) 이 정책 제거 + 서버에서 service_role 로만 조회 + leads_public_insert 를 SECURITY DEFINER 함수로 대체.
--    참고: 앱 코드(selectMyProjects/ById)는 이 공개 정책과 섞이지 않도록 owner 를 명시적으로 필터한다.

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

-- ───────────────────────── compliance_logs ─────────────────────────
-- 게시 승인 감사 로그: 승인할 때마다 승인 기록 + 그때의 카피·템플릿 스냅샷을 쌓는다(덮어쓰지 않음).
-- 실증 자료 제출 요구(실증고시: 15일 이내) 등에 "무엇을 언제 누가 승인했는지"를 보여 주기 위함.
-- 프로젝트를 지워도 로그는 남는다(project_id 만 null).
create table if not exists public.compliance_logs (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid references public.projects (id) on delete set null,
  owner       uuid not null references auth.users (id) on delete cascade,
  record      jsonb not null,
  template    text not null default '',
  copy        jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create index if not exists compliance_logs_project_idx on public.compliance_logs (project_id);

alter table public.compliance_logs enable row level security;

-- 소유자만 조회·추가. 수정·삭제 정책은 두지 않는다(감사 로그는 append-only).
drop policy if exists "compliance_logs_owner_select" on public.compliance_logs;
create policy "compliance_logs_owner_select" on public.compliance_logs
  for select using (auth.uid() = owner);

drop policy if exists "compliance_logs_owner_insert" on public.compliance_logs;
create policy "compliance_logs_owner_insert" on public.compliance_logs
  for insert with check (
    auth.uid() = owner
    and exists (select 1 from public.projects p where p.id = compliance_logs.project_id and p.owner = auth.uid())
  );

-- ───────────────────────── page_stats ─────────────────────────
-- 공개 페이지 방문 집계(일·유입 경로 단위 카운터). 개인 식별 정보(IP·UA)는 저장하지 않는다.
-- 방문 기록은 아래 record_page_view() 함수로만 증가시킨다(직접 insert/update 정책 없음).
create table if not exists public.page_stats (
  project_id  uuid not null references public.projects (id) on delete cascade,
  day         date not null,
  source      text not null,
  views       integer not null default 0,
  primary key (project_id, day, source)
);

alter table public.page_stats enable row level security;

drop policy if exists "page_stats_owner_select" on public.page_stats;
create policy "page_stats_owner_select" on public.page_stats
  for select using (
    exists (select 1 from public.projects p where p.id = page_stats.project_id and p.owner = auth.uid())
  );

-- 게시된 프로젝트에 한해 오늘(KST)·경로 카운터를 1 올린다. 경로 값은 앱의 고정 목록(lib/analytics/source.ts)만 허용.
create or replace function public.record_page_view(p_project uuid, p_source text)
returns void
language plpgsql
security definer set search_path = public
as $$
declare
  v_source text := p_source;
begin
  if v_source is null or v_source not in
     ('naver','instagram','kakao','threads','youtube','google','daum','facebook','direct','other') then
    v_source := 'other';
  end if;
  if not exists (select 1 from public.projects where id = p_project and published = true) then
    return;
  end if;
  insert into public.page_stats (project_id, day, source, views)
  values (p_project, (now() at time zone 'Asia/Seoul')::date, v_source, 1)
  on conflict (project_id, day, source) do update set views = public.page_stats.views + 1;
end;
$$;

revoke all on function public.record_page_view(uuid, text) from public;
grant execute on function public.record_page_view(uuid, text) to anon, authenticated;

-- ───────────────────────── api_tokens ─────────────────────────
-- AI 에이전트(MCP) 연동용 개인 액세스 토큰. 원문은 발급 순간에만 보여 주고 SHA-256 해시만 저장한다.
-- MCP 서버는 service_role 키로 해시를 조회해 소유자를 찾고, 이후 모든 조회를 owner 로 명시 필터한다.
create table if not exists public.api_tokens (
  id            uuid primary key default gen_random_uuid(),
  owner         uuid not null references auth.users (id) on delete cascade,
  name          text not null default '',
  token_hash    text not null unique,
  prefix        text not null default '',
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz,
  revoked_at    timestamptz
);

create index if not exists api_tokens_owner_idx on public.api_tokens (owner);

alter table public.api_tokens enable row level security;

drop policy if exists "api_tokens_owner_all" on public.api_tokens;
create policy "api_tokens_owner_all" on public.api_tokens
  for all using (auth.uid() = owner) with check (auth.uid() = owner);
