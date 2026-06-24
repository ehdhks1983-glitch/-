// lib/gateway/index.ts — AI 게이트웨이 (스펙 §8: 핵심 제약).
// 모든 AI 호출은 이 모듈만 경유한다. 기능 코드에서 SDK 직접 호출 금지.
// 책임: 모델 선택(티어) · 호출 · 재시도 · 토큰/원가 계산 · 캐싱.
//   - 모델·단가는 lib/config/models.ts (하드코딩/매직넘버 금지, §13).
//   - costUsd 는 호출자(워커/과금)가 usage_events.ai_cost_usd 에 기록한다(§12.3은 spend와 한 트랜잭션).
//     게이트웨이는 DB를 건드리지 않고 cost 를 "계산"만 한다.
//   - 키리스(ANTHROPIC_API_KEY 없음 / GOMDAERI_MOCK=1): 결정적 목 + 합성 토큰으로 동작.

import Anthropic from "@anthropic-ai/sdk";
import {
  GATEWAY_CONFIG,
  TIER_MAX_TOKENS,
  type GatewayTask,
  type Tier,
  computeCostUsd,
  modelForTask,
  tierForTask,
} from "@/lib/config/models";

export interface GenerateArgs {
  task: GatewayTask;
  system: string;
  input: string;
  /** 프롬프트 캐싱(system 블록) + 단기 응답 캐시 사용. 재생성은 false(매번 새 변형). */
  cacheable?: boolean;
  /** JSON 응답 기대 힌트(파싱은 호출자). */
  json?: boolean;
  /** 출력 토큰 상한 override (기본: 티어별). */
  maxTokens?: number;
  /** 변형 다양성용 temperature(재생성 시 ↑). 기본 0.7. */
  temperature?: number;
  /** 키리스 목 모드에서 반환할 텍스트(각 생성기가 자기 스키마에 맞는 샘플 제공). */
  mock?: string;
}

export interface Usage {
  inputTokens: number;
  outputTokens: number;
}

export interface GenerateResult {
  text: string;
  usage: Usage;
  costUsd: number;
  model: string;
  tier: Tier;
  /** 목 모드로 생성됨. */
  mocked: boolean;
  /** 단기 응답 캐시 히트(새 API 비용 0). */
  cached: boolean;
}

/** 키 없음 또는 강제 목 → 목 모드. */
export function isMockMode(): boolean {
  if (process.env.GOMDAERI_MOCK === "1") return true;
  return !(process.env.ANTHROPIC_API_KEY ?? "").trim();
}

/**
 * 단일 AI 생성 호출. 모델 티어링·재시도·원가계산·캐싱을 캡슐화.
 * 실패 시(재시도 소진) throw → 호출자가 채널 실패(partial)로 처리.
 */
export async function generate(args: GenerateArgs): Promise<GenerateResult> {
  const tier = tierForTask(args.task);
  const model = modelForTask(args.task);
  const maxTokens = args.maxTokens ?? TIER_MAX_TOKENS[tier];

  // 1) 단기 응답 캐시(cacheable 한정) — 중복/더블클릭 방지. 히트 시 새 비용 0.
  if (args.cacheable) {
    const hit = cacheGet(cacheKey(args));
    if (hit) return { ...hit, cached: true, costUsd: 0 };
  }

  // 2) 목 모드
  if (isMockMode()) {
    const text = (args.mock ?? `[mock:${args.task}]`).trim();
    const usage: Usage = {
      inputTokens: estimateTokens(args.system + args.input),
      outputTokens: estimateTokens(text),
    };
    const result: GenerateResult = {
      text,
      usage,
      costUsd: computeCostUsd(tier, usage.inputTokens, usage.outputTokens),
      model,
      tier,
      mocked: true,
      cached: false,
    };
    if (args.cacheable) cacheSet(cacheKey(args), result);
    return result;
  }

  // 3) 실호출 + 재시도
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY ?? "", maxRetries: 0 });
  const system = args.cacheable
    ? [{ type: "text" as const, text: args.system, cache_control: { type: "ephemeral" as const } }]
    : args.system;

  let lastErr: unknown;
  for (let attempt = 0; attempt <= GATEWAY_CONFIG.maxRetries; attempt++) {
    try {
      const res = await withTimeout(
        client.messages.create({
          model,
          max_tokens: maxTokens,
          temperature: args.temperature ?? 0.7,
          system,
          messages: [{ role: "user", content: args.input }],
        }),
        GATEWAY_CONFIG.requestTimeoutMs,
      );

      const text = res.content
        .map((b) => (b.type === "text" ? b.text : ""))
        .join("")
        .trim();
      if (!text) throw new Error("빈 응답");

      const usage = extractUsage(res.usage);
      const result: GenerateResult = {
        text,
        usage,
        costUsd: computeCostUsd(tier, usage.inputTokens, usage.outputTokens),
        model,
        tier,
        mocked: false,
        cached: false,
      };
      if (args.cacheable) cacheSet(cacheKey(args), result);
      return result;
    } catch (err) {
      lastErr = err;
      const msg = err instanceof Error ? err.message : String(err);
      if (process.env.NODE_ENV !== "production") {
        console.warn(`[gateway] ${model} 실패(시도 ${attempt + 1}): ${msg}`);
      }
      if (attempt < GATEWAY_CONFIG.maxRetries) {
        await sleep(GATEWAY_CONFIG.retryBackoffMs * 2 ** attempt);
      }
    }
  }
  throw new Error(
    `게이트웨이 호출 실패 (task=${args.task}, model=${model}): ${
      lastErr instanceof Error ? lastErr.message : String(lastErr)
    }`,
  );
}

// ───────────────────────── 토큰/원가 ─────────────────────────

/** Anthropic usage → {input,output}. 캐시 토큰도 input에 합산(보수적). */
function extractUsage(u: Anthropic.Usage | undefined): Usage {
  const input =
    (u?.input_tokens ?? 0) +
    (u?.cache_read_input_tokens ?? 0) +
    (u?.cache_creation_input_tokens ?? 0);
  return { inputTokens: input, outputTokens: u?.output_tokens ?? 0 };
}

/** 목 모드용 대략 토큰 추정(≈ 4 chars/token). 원가계산 데모 용도. */
function estimateTokens(s: string): number {
  return Math.max(1, Math.ceil((s?.length ?? 0) / 4));
}

// ───────────────────────── 단기 응답 캐시 ─────────────────────────
// 인메모리 TTL 캐시. cacheable 호출의 우발적 중복(더블클릭/재시도)만 흡수.
// 재생성(cacheable=false)에는 적용 안 됨 → 변형 다양성 유지.

interface CacheEntry {
  at: number;
  result: GenerateResult;
}
const RESPONSE_CACHE = new Map<string, CacheEntry>();
const CACHE_TTL_MS = Number(process.env.AI_CACHE_TTL_MS) > 0 ? Number(process.env.AI_CACHE_TTL_MS) : 60_000;
const CACHE_MAX = 200;

function cacheKey(a: GenerateArgs): string {
  return `${a.task}::${a.maxTokens ?? ""}::${a.temperature ?? ""}::${hash(a.system)}::${hash(a.input)}`;
}

function cacheGet(key: string): GenerateResult | null {
  const e = RESPONSE_CACHE.get(key);
  if (!e) return null;
  if (Date.now() - e.at > CACHE_TTL_MS) {
    RESPONSE_CACHE.delete(key);
    return null;
  }
  return e.result;
}

function cacheSet(key: string, result: GenerateResult): void {
  if (RESPONSE_CACHE.size >= CACHE_MAX) {
    const oldest = RESPONSE_CACHE.keys().next().value;
    if (oldest) RESPONSE_CACHE.delete(oldest);
  }
  RESPONSE_CACHE.set(key, { at: Date.now(), result });
}

/** 가벼운 문자열 해시(djb2). 캐시 키 용도(충돌은 task/길이로 충분히 분리). */
function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// ───────────────────────── 유틸 ─────────────────────────

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const id = setTimeout(() => reject(new Error(`타임아웃 ${ms}ms 초과`)), ms);
    p.then(
      (v) => {
        clearTimeout(id);
        resolve(v);
      },
      (e) => {
        clearTimeout(id);
        reject(e);
      },
    );
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** 모델 응답에서 JSON 객체만 안전 추출(코드펜스/잡텍스트 방어). 생성기들이 공용으로 쓴다. */
export function safeParseJson<T>(text: string): T {
  let t = (text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  const a = t.indexOf("{");
  const b = t.lastIndexOf("}");
  if (a !== -1 && b !== -1 && b > a) t = t.slice(a, b + 1);
  return JSON.parse(t) as T;
}
