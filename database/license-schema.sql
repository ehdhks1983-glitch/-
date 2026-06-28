-- database/license-schema.sql  [신규]
-- 통합 라이선스(올인원) 스키마: licenses / license_activations / license_checks.
-- PromptSite 의 schema.sql 과 독립적이다. Supabase SQL Editor 에 그대로 붙여 실행하세요.
-- (재실행 안전: IF NOT EXISTS / DROP ... IF EXISTS 사용)
--
-- 보안 모델: 이 세 테이블은 RLS 를 켜두되 어떤 정책도 만들지 않는다.
--   → anon/로그인(authenticated) 세션으로는 일절 접근 불가.
--   → 오직 service_role(서버의 createSupabaseAdmin) 만 RLS 를 우회해 접근한다.
--   관리 화면/봇 검증은 전부 서버에서 service_role 로만 수행된다.

-- ───────────────────────── licenses(발급 코드) ─────────────────────────
create table if not exists public.licenses (
  id           uuid primary key default gen_random_uuid(),
  code         text not null unique,                 -- ALLB-XXXXX-XXXXX-XXXXX
  label        text not null default '',             -- 고객/메모용 표시 이름
  status       text not null default 'active',       -- 'active' | 'revoked'
  max_devices  integer not null default 1,           -- 동시 사용 허용 기기 수
  expires_at   timestamptz,                          -- null = 무기한
  note         text not null default '',             -- 관리자 메모
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists licenses_code_idx on public.licenses (code);
create index if not exists licenses_status_idx on public.licenses (status);

alter table public.licenses enable row level security;
-- (의도적으로 정책 없음 → service_role 전용)

-- ───────────────────── license_activations(기기 바인딩) ─────────────────────
create table if not exists public.license_activations (
  id            uuid primary key default gen_random_uuid(),
  license_id    uuid not null references public.licenses (id) on delete cascade,
  device_id     text not null,                       -- 봇이 보내는 하드웨어 지문
  device_label  text not null default '',            -- 호스트명 등(표시용)
  last_bot_id   text not null default '',            -- 마지막으로 호출한 봇 id
  first_seen_at timestamptz not null default now(),
  last_seen_at  timestamptz not null default now(),
  unique (license_id, device_id)
);

create index if not exists activations_license_idx on public.license_activations (license_id);

alter table public.license_activations enable row level security;
-- (의도적으로 정책 없음 → service_role 전용)

-- ───────────────────── license_checks(검증 호출 로그) ─────────────────────
create table if not exists public.license_checks (
  id          uuid primary key default gen_random_uuid(),
  license_id  uuid references public.licenses (id) on delete cascade,
  device_id   text,
  bot_id      text,
  reason      text not null,                         -- ok / not_found / revoked / expired / device_limit ...
  created_at  timestamptz not null default now()
);

create index if not exists checks_license_idx on public.license_checks (license_id);
create index if not exists checks_created_idx on public.license_checks (created_at);

alter table public.license_checks enable row level security;
-- (의도적으로 정책 없음 → service_role 전용)
