-- database/multipublish_schema.sql  [신규 — 곰대리 멀티발행 MVP]
-- 스펙 §6 데이터모델 + §12 포인트/과금. Supabase SQL Editor에 붙여 실행.
-- 적용 순서: 1) schema.sql (profiles/projects/leads)  2) 이 파일.
--   이 파일의 handle_new_user 는 schema.sql 버전을 대체(superset): profile + wallet + trial 구독 + 체험 grant.
-- 재실행 안전(IF NOT EXISTS / create or replace / drop policy if exists).

-- ╔═══════════════════════════════════════════════════════════╗
-- ║ 1층 (플랫폼): plans / products / subscriptions / 포인트     ║
-- ╚═══════════════════════════════════════════════════════════╝

-- ───────────── plans (정책값의 단일 출처 — 스펙 §6) ─────────────
create table if not exists public.plans (
  id                       uuid primary key default gen_random_uuid(),
  code                     text not null unique,            -- 'trial' / 'starter' / ...
  name                     text not null default '',
  monthly_points           int  not null default 0,         -- 월 지급(= 가입 체험 grant 정책값)
  carryover_cap_multiplier numeric not null default 2,       -- 이월 상한 = 월지급 × 2 (스펙 §2)
  retention_days           int  not null default 90,         -- 보관 일수 (스펙 §2)
  retention_max_items      int  not null default 100,        -- 보관 개수 (스펙 §2)
  price_krw                int,                               -- 비움(P2) — nullable
  created_at               timestamptz not null default now()
);

-- ───────────── products (제품 N개 전제 — 스펙 §1/§6) ─────────────
create table if not exists public.products (
  id          uuid primary key default gen_random_uuid(),
  code        text not null unique,                          -- 'multipublish'
  name        text not null default '',
  created_at  timestamptz not null default now()
);

-- ───────────── subscriptions (MVP 최소 — 결제연동 P2) ─────────────
create table if not exists public.subscriptions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  plan_id     uuid not null references public.plans (id),
  status      text not null default 'active',                -- active / canceled / past_due
  period_end  timestamptz,
  created_at  timestamptz not null default now()
);
create index if not exists subscriptions_user_idx on public.subscriptions (user_id);

-- ───────────── point_wallets (잔액 캐시 — 진실은 원장) ─────────────
create table if not exists public.point_wallets (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  balance     int not null default 0 check (balance >= 0),   -- 음수 잔액 금지 (스펙 §12)
  updated_at  timestamptz not null default now()
);

-- ───────────── point_transactions (원장 = 진실 — 스펙 §6/§12) ─────────────
create table if not exists public.point_transactions (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  type           text not null,                              -- grant/spend/refund/expire/carryover
  amount         int  not null,                              -- +grant / -spend
  balance_after  int  not null,
  product_id     uuid references public.products (id),
  ref            text,                                       -- 예: generation id
  metadata       jsonb not null default '{}'::jsonb,
  created_at     timestamptz not null default now()
);
create index if not exists point_tx_user_idx on public.point_transactions (user_id, created_at desc);

-- ───────────── usage_events (실측 원가 기록 — 스펙 §5/§6) ─────────────
create table if not exists public.usage_events (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  action          text not null,                             -- generate_set / regenerate_*
  points_charged  int  not null default 0,
  ai_cost_usd     numeric(14,8) not null default 0,          -- 실제 AI 원가(스펙 §8)
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);
create index if not exists usage_events_user_idx on public.usage_events (user_id, created_at desc);

-- ╔═══════════════════════════════════════════════════════════╗
-- ║ 2층 (제품): generations / generation_outputs               ║
-- ╚═══════════════════════════════════════════════════════════╝

create table if not exists public.generations (
  id           uuid primary key default gen_random_uuid(),
  owner        uuid not null references auth.users (id) on delete cascade,
  product_id   uuid references public.products (id),
  keyword      text not null,
  title        text not null default '',
  source_refs  jsonb not null default '[]'::jsonb,           -- SourceRef[]
  options      jsonb not null default '{}'::jsonb,           -- GenOptions(tone/monetize/channels)
  core         jsonb,                                        -- Core (수정 가능)
  status       text not null default 'queued',               -- queued/processing/done/partial/failed
  error        text,
  starred      boolean not null default false,               -- 별표 보관 예외 (스펙 §2)
  expires_at   timestamptz,                                  -- 보관 만료(앱이 plan.retention_days로 설정)
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists generations_owner_idx  on public.generations (owner, created_at desc);
create index if not exists generations_status_idx on public.generations (status);

create table if not exists public.generation_outputs (
  id             uuid primary key default gen_random_uuid(),
  generation_id  uuid not null references public.generations (id) on delete cascade,
  channel        text not null,                              -- blog/threads/instagram/cafe/shorts
  variant_no     int  not null default 1,                    -- 재생성 시 증가
  status         text not null default 'done',               -- done/failed
  content        jsonb not null default '{}'::jsonb,
  fact_check     jsonb,                                      -- P2
  ai_cost_usd    numeric(14,8) not null default 0,
  created_at     timestamptz not null default now()
);
create index if not exists gen_outputs_gen_idx on public.generation_outputs (generation_id, channel, variant_no desc);

-- ───────────── updated_at 자동 갱신 ─────────────
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists generations_touch on public.generations;
create trigger generations_touch before update on public.generations
  for each row execute function public.touch_updated_at();

-- ╔═══════════════════════════════════════════════════════════╗
-- ║ 과금 함수 (원자적 — 스펙 §12)                               ║
-- ╚═══════════════════════════════════════════════════════════╝

-- grant: 지갑 증가 + 원장 1건. (가입 체험/월 지급)
create or replace function public.grant_points(
  p_user_id uuid,
  p_points  int,
  p_metadata jsonb default '{}'::jsonb
) returns int
language plpgsql security definer set search_path = public as $$
declare v_new int;
begin
  if p_points <= 0 then raise exception 'grant points must be > 0'; end if;

  insert into public.point_wallets(user_id, balance)
  values (p_user_id, p_points)
  on conflict (user_id) do update
    set balance = public.point_wallets.balance + excluded.balance, updated_at = now()
  returning balance into v_new;

  insert into public.point_transactions(user_id, type, amount, balance_after, metadata)
  values (p_user_id, 'grant', p_points, v_new, coalesce(p_metadata, '{}'::jsonb));

  return v_new;
end; $$;

-- spend: 원자적 차감(잔액≥비용 가드) + 원장 + usage_event 한 트랜잭션. (스펙 §12.3)
-- 잔액 부족이면 'insufficient_points' 예외 → 호출자가 차감 0으로 처리.
create or replace function public.spend_points(
  p_user_id      uuid,
  p_points       int,
  p_action       text,
  p_ai_cost      numeric default 0,
  p_product_code text default 'multipublish',
  p_ref          text default null,
  p_metadata     jsonb default '{}'::jsonb
) returns int
language plpgsql security definer set search_path = public as $$
declare
  v_new     int;
  v_product uuid;
begin
  if p_points < 0 then raise exception 'spend points must be >= 0'; end if;
  select id into v_product from public.products where code = p_product_code;

  -- balance >= cost 인 행만 갱신 → 동시성 하에서도 이중차감/음수 방지(스펙 §12 동시성).
  update public.point_wallets
     set balance = balance - p_points, updated_at = now()
   where user_id = p_user_id and balance >= p_points
  returning balance into v_new;

  if not found then
    raise exception 'insufficient_points' using errcode = 'P0001';
  end if;

  insert into public.point_transactions(user_id, type, amount, balance_after, product_id, ref, metadata)
  values (p_user_id, 'spend', -p_points, v_new, v_product, p_ref, coalesce(p_metadata, '{}'::jsonb));

  insert into public.usage_events(user_id, action, points_charged, ai_cost_usd, metadata)
  values (p_user_id, p_action, p_points, coalesce(p_ai_cost, 0), coalesce(p_metadata, '{}'::jsonb));

  return v_new;
end; $$;

-- 잔액 조회 헬퍼(없으면 0).
create or replace function public.wallet_balance(p_user_id uuid)
returns int language sql stable security definer set search_path = public as $$
  select coalesce((select balance from public.point_wallets where user_id = p_user_id), 0);
$$;

-- 큐 점유: 가장 오래된 queued 1건을 processing 으로(FOR UPDATE SKIP LOCKED = 동시 워커 안전).
create or replace function public.claim_next_generation()
returns public.generations
language plpgsql security definer set search_path = public as $$
declare v_row public.generations;
begin
  select * into v_row from public.generations
   where status = 'queued'
   order by created_at
   for update skip locked
   limit 1;
  if not found then return null; end if;
  update public.generations set status = 'processing', updated_at = now()
   where id = v_row.id returning * into v_row;
  return v_row;
end; $$;

-- 과금 함수는 서버(워커=service_role)만 호출. 일반 사용자 직접 호출 차단.
revoke all on function public.grant_points(uuid, int, jsonb) from public, anon, authenticated;
revoke all on function public.spend_points(uuid, int, text, numeric, text, text, jsonb) from public, anon, authenticated;
grant execute on function public.grant_points(uuid, int, jsonb) to service_role;
grant execute on function public.spend_points(uuid, int, text, numeric, text, text, jsonb) to service_role;
grant execute on function public.wallet_balance(uuid) to authenticated, service_role;
revoke all on function public.claim_next_generation() from public, anon, authenticated;
grant execute on function public.claim_next_generation() to service_role;

-- ╔═══════════════════════════════════════════════════════════╗
-- ║ 가입 트리거: profile + wallet + trial 구독 + 체험 grant     ║
-- ╚═══════════════════════════════════════════════════════════╝
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare v_plan public.plans%rowtype;
begin
  insert into public.profiles(id, email) values (new.id, new.email) on conflict (id) do nothing;
  insert into public.point_wallets(user_id, balance) values (new.id, 0) on conflict (user_id) do nothing;

  select * into v_plan from public.plans where code = 'trial' limit 1;
  if found then
    insert into public.subscriptions(user_id, plan_id, status, period_end)
    values (new.id, v_plan.id, 'active', now() + interval '30 days');
    if v_plan.monthly_points > 0 then
      perform public.grant_points(new.id, v_plan.monthly_points, jsonb_build_object('reason', 'signup_trial'));
    end if;
  end if;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users for each row execute function public.handle_new_user();

-- ╔═══════════════════════════════════════════════════════════╗
-- ║ RLS — 본인 리소스만(스펙 §11). 쓰기는 함수/서버(service_role).║
-- ╚═══════════════════════════════════════════════════════════╝

-- 참조 데이터(plans/products): 로그인 사용자 읽기 허용.
alter table public.plans    enable row level security;
alter table public.products enable row level security;
drop policy if exists plans_read on public.plans;
create policy plans_read on public.plans for select to authenticated using (true);
drop policy if exists products_read on public.products;
create policy products_read on public.products for select to authenticated using (true);

-- 포인트/구독/사용: 본인 행만 읽기. 쓰기 정책 없음(SECURITY DEFINER 함수/service_role 전용).
alter table public.subscriptions      enable row level security;
alter table public.point_wallets      enable row level security;
alter table public.point_transactions enable row level security;
alter table public.usage_events       enable row level security;

drop policy if exists subscriptions_select_own on public.subscriptions;
create policy subscriptions_select_own on public.subscriptions for select using (auth.uid() = user_id);
drop policy if exists wallets_select_own on public.point_wallets;
create policy wallets_select_own on public.point_wallets for select using (auth.uid() = user_id);
drop policy if exists tx_select_own on public.point_transactions;
create policy tx_select_own on public.point_transactions for select using (auth.uid() = user_id);
drop policy if exists usage_select_own on public.usage_events;
create policy usage_select_own on public.usage_events for select using (auth.uid() = user_id);

-- generations: 소유자 select/insert/update/delete. (insert/update는 사용자 세션 경유 가능)
alter table public.generations enable row level security;
drop policy if exists generations_select_own on public.generations;
create policy generations_select_own on public.generations for select using (auth.uid() = owner);
drop policy if exists generations_insert_own on public.generations;
create policy generations_insert_own on public.generations for insert with check (auth.uid() = owner);
drop policy if exists generations_update_own on public.generations;
create policy generations_update_own on public.generations for update using (auth.uid() = owner) with check (auth.uid() = owner);
drop policy if exists generations_delete_own on public.generations;
create policy generations_delete_own on public.generations for delete using (auth.uid() = owner);

-- generation_outputs: 본인 generation의 산출물만 select. 쓰기는 워커(service_role).
alter table public.generation_outputs enable row level security;
drop policy if exists gen_outputs_select_own on public.generation_outputs;
create policy gen_outputs_select_own on public.generation_outputs for select using (
  exists (select 1 from public.generations g where g.id = generation_outputs.generation_id and g.owner = auth.uid())
);

-- ╔═══════════════════════════════════════════════════════════╗
-- ║ 시드 (정책값 — lib/config 와 동일해야 함)                   ║
-- ╚═══════════════════════════════════════════════════════════╝
insert into public.products (code, name)
values ('multipublish', '멀티발행')
on conflict (code) do nothing;

-- trial.monthly_points = 30 (= lib/config/points.ts SIGNUP_GRANT_POINTS). 이월 상한 ×2, 보관 90일·100개.
insert into public.plans (code, name, monthly_points, carryover_cap_multiplier, retention_days, retention_max_items, price_krw)
values ('trial', '체험', 30, 2, 90, 100, null)
on conflict (code) do nothing;
