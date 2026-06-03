// lib/ai/config.ts  [기존 — promptsite-ai-core] (모델ID는 빌드 시점 1회 확인 — 핸드오프 5장)
// 모델ID·타임아웃·재시도·키는 전부 여기서만 관리한다(하드코딩/매직넘버 금지 규칙).
// 폴백 체인: 상위(품질/주력) → 하위(비용/속도/대체 프로바이더). core.ts가 순서대로 시도한다.

export type Provider = "anthropic" | "google" | "openai";

/** 파이프라인 작업 종류. analyze 체인은 clarify도 함께 사용한다. */
export type TaskKind = "analyze" | "copy";

export interface ModelSpec {
  provider: Provider;
  model: string;
  maxTokens: number;
}

/** 환경변수에서 키를 읽되 기본값은 빈 문자열(시크릿 규칙). 빈 키 프로바이더는 core가 자동 skip. */
export const API_KEYS: Record<Provider, string> = {
  anthropic: process.env.ANTHROPIC_API_KEY ?? "",
  google: process.env.GEMINI_API_KEY ?? process.env.GOOGLE_API_KEY ?? "",
  openai: process.env.OPENAI_API_KEY ?? "",
};

/** 호출 동작 파라미터(매직넘버 금지 → 여기로). 전부 env로 override 가능. */
export const GEN_CONFIG = {
  /** 모델 1회 호출 타임아웃(ms). 초과 시 다음 모델로 폴백. */
  requestTimeoutMs: numEnv("AI_TIMEOUT_MS", 60_000),
  /** 같은 모델 재시도 횟수(이후 다음 모델로 폴백). */
  maxRetriesPerModel: numEnv("AI_MAX_RETRIES", 1),
  /** 재시도 백오프 기준(ms). 시도마다 *2. */
  retryBackoffMs: numEnv("AI_RETRY_BACKOFF_MS", 800),
};

/**
 * 모델 ID. 2026.6 기준 기본값이며 env로 덮어쓸 수 있다.
 * - Claude: claude-opus-4-8 / claude-sonnet-4-6
 * - Gemini: gemini-3.1-pro / gemini-3.5-flash
 * - OpenAI(텍스트): 핸드오프엔 텍스트 모델ID 미명시 → 기본값은 빌드 시 확인 필요(OPENAI_TEXT_MODEL로 override).
 */
const MODEL_IDS = {
  claudePrimary: process.env.ANTHROPIC_MODEL_PRIMARY ?? "claude-opus-4-8",
  claudeSecondary: process.env.ANTHROPIC_MODEL_SECONDARY ?? "claude-sonnet-4-6",
  geminiPrimary: process.env.GEMINI_MODEL_PRIMARY ?? "gemini-3.1-pro",
  geminiSecondary: process.env.GEMINI_MODEL_SECONDARY ?? "gemini-3.5-flash",
  openaiText: process.env.OPENAI_TEXT_MODEL ?? "gpt-5.1",
};

/** 작업별 폴백 체인(상위→하위). */
export const MODEL_CHAINS: Record<TaskKind, ModelSpec[]> = {
  // 카피 = 제품 핵심 IP. 품질 우선: Opus → Sonnet → Gemini Pro → OpenAI
  copy: [
    { provider: "anthropic", model: MODEL_IDS.claudePrimary, maxTokens: 4096 },
    { provider: "anthropic", model: MODEL_IDS.claudeSecondary, maxTokens: 4096 },
    { provider: "google", model: MODEL_IDS.geminiPrimary, maxTokens: 4096 },
    { provider: "openai", model: MODEL_IDS.openaiText, maxTokens: 4096 },
  ],
  // 분석/보완질문 = 비용·속도 우선: Sonnet → Gemini Flash → OpenAI
  analyze: [
    { provider: "anthropic", model: MODEL_IDS.claudeSecondary, maxTokens: 2048 },
    { provider: "google", model: MODEL_IDS.geminiSecondary, maxTokens: 2048 },
    { provider: "openai", model: MODEL_IDS.openaiText, maxTokens: 2048 },
  ],
};

function numEnv(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
}
