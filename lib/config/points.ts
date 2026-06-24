// lib/config/points.ts
// 포인트 비용 상수 (스펙 §7) — 매직넘버 금지 규칙(§13)에 따라 전부 여기로.
// 단가/정책이 바뀌면 이 파일 또는 plans 테이블만 수정한다.

/** 액션별 포인트 차감량. */
export const POINTS = {
  /** 1세트 = 블로그 + 4채널 (스펙 §7). */
  SET: 10,
  /** 블로그만 재생성. */
  BLOG_REGEN: 5,
  /** 채널 1개 재생성. */
  CHANNEL_REGEN: 2,
  /** 코어만 다시. */
  CORE_REGEN: 2,
} as const;

/**
 * 가입 체험 grant (스펙 §10/§12 "예: 30P").
 * 실제 정책값의 단일 출처는 plans.monthly_points(trial) 컬럼이다(스펙 §6 "정책값은 plans 컬럼").
 * 이 상수는 (a) SQL 시드와 동일해야 하며 (b) Supabase 미설정(키리스) 인메모리 지갑 기본값으로 쓰인다.
 */
export const SIGNUP_GRANT_POINTS = 30;

/** usage_events.action 값 (스펙 §6). */
export const USAGE_ACTION = {
  GENERATE_SET: "generate_set",
  REGEN_BLOG: "regenerate_blog",
  REGEN_CHANNEL: "regenerate_channel",
  REGEN_CORE: "regenerate_core",
} as const;

/** point_transactions.type 값 (원장 유형, 스펙 §6). */
export const TX_TYPE = {
  GRANT: "grant",
  SPEND: "spend",
  REFUND: "refund",
  EXPIRE: "expire",
  CARRYOVER: "carryover",
} as const;
