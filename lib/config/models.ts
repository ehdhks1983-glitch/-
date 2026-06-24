// lib/config/models.ts
// AI 모델 티어링 · 단가 · 호출 동작 (스펙 §8). 매직넘버/하드코딩 금지(§13).
// 모델·단가가 바뀌면 게이트웨이 코드가 아니라 이 파일(또는 env)만 수정한다.

/** 게이트웨이 task 종류 (스펙 §8 매핑의 키). */
export type GatewayTask =
  | "core"
  | "blog"
  | "factcheck"
  | "channel.threads"
  | "channel.instagram"
  | "channel.cafe"
  | "channel.shorts";

/** 모델 티어. */
export type Tier = "haiku" | "sonnet";

function strEnv(name: string, fallback: string): string {
  const v = process.env[name];
  return v && v.trim() ? v.trim() : fallback;
}

function numEnv(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v >= 0 ? v : fallback;
}

/**
 * 티어별 모델 ID. 2026 기준 기본값이며 env로 덮어쓸 수 있다(스펙 §8: 정확 ID는 빌드 시 확정).
 * - Haiku  = claude-haiku-4-5
 * - Sonnet = claude-sonnet-4-6
 */
export const TIER_MODEL: Record<Tier, string> = {
  haiku: strEnv("ANTHROPIC_MODEL_HAIKU", "claude-haiku-4-5"),
  sonnet: strEnv("ANTHROPIC_MODEL_SONNET", "claude-sonnet-4-6"),
};

/**
 * task → 티어 매핑 (스펙 §8):
 *   core → haiku · blog → sonnet · channel.* → haiku · factcheck → haiku
 */
export function tierForTask(task: GatewayTask): Tier {
  return task === "blog" ? "sonnet" : "haiku";
}

/** task → 모델 ID. */
export function modelForTask(task: GatewayTask): string {
  return TIER_MODEL[tierForTask(task)];
}

export interface TierPricing {
  /** input(prompt) 토큰 백만개당 USD. */
  inputPerMTok: number;
  /** output(completion) 토큰 백만개당 USD. */
  outputPerMTok: number;
}

/**
 * 티어별 단가 (스펙 §8: Haiku $1/$5, Sonnet $3/$15 per MTok).
 * 단가 변경 시 env 또는 여기만 수정 → usage_events.ai_cost_usd 자동 반영.
 */
export const TIER_PRICING: Record<Tier, TierPricing> = {
  haiku: { inputPerMTok: numEnv("PRICE_HAIKU_IN", 1), outputPerMTok: numEnv("PRICE_HAIKU_OUT", 5) },
  sonnet: { inputPerMTok: numEnv("PRICE_SONNET_IN", 3), outputPerMTok: numEnv("PRICE_SONNET_OUT", 15) },
};

/** 토큰 사용량 → USD 원가. (스펙 §8: 토큰 × 단가) */
export function computeCostUsd(tier: Tier, inputTokens: number, outputTokens: number): number {
  const p = TIER_PRICING[tier];
  const cost = (inputTokens / 1_000_000) * p.inputPerMTok + (outputTokens / 1_000_000) * p.outputPerMTok;
  // 부동소수 오차 정리(소수 8자리 = usage_events 컬럼 정밀도와 일치).
  return Math.round(cost * 1e8) / 1e8;
}

/** 티어별 max output tokens (블로그가 가장 길다). env override. */
export const TIER_MAX_TOKENS: Record<Tier, number> = {
  haiku: numEnv("AI_MAX_TOKENS_HAIKU", 2048),
  sonnet: numEnv("AI_MAX_TOKENS_SONNET", 4096),
};

/** 게이트웨이 호출 동작 (타임아웃/재시도/백오프). 전부 env override. */
export const GATEWAY_CONFIG = {
  requestTimeoutMs: numEnv("AI_TIMEOUT_MS", 60_000),
  maxRetries: numEnv("AI_MAX_RETRIES", 2),
  retryBackoffMs: numEnv("AI_RETRY_BACKOFF_MS", 800),
};
