// lib/rateLimit.ts  [신규]
// 단순 인메모리 고정 윈도우 카운터. 서버리스에선 인스턴스별이라 완벽하진 않지만
// 토큰 비용 폭주를 막는 1차 방어로는 충분. 분산 환경은 추후 Upstash 등으로 교체.

interface Bucket {
  count: number;
  resetAt: number;
}

const buckets = new Map<string, Bucket>();

export interface RateLimitResult {
  ok: boolean;
  remaining: number;
  retryAfterSec: number;
}

/** key 기준으로 windowMs 동안 limit 회까지 허용. */
export function rateLimit(key: string, limit: number, windowMs: number): RateLimitResult {
  const now = Date.now();
  const b = buckets.get(key);
  if (!b || now >= b.resetAt) {
    buckets.set(key, { count: 1, resetAt: now + windowMs });
    return { ok: true, remaining: limit - 1, retryAfterSec: 0 };
  }
  if (b.count >= limit) {
    return { ok: false, remaining: 0, retryAfterSec: Math.ceil((b.resetAt - now) / 1000) };
  }
  b.count += 1;
  return { ok: true, remaining: limit - b.count, retryAfterSec: 0 };
}

/** 요청에서 클라이언트 식별자(IP) 추출. 프록시 헤더 우선. */
export function clientKey(req: Request, prefix = ""): string {
  const xff = req.headers.get("x-forwarded-for") ?? "";
  const ip = xff.split(",")[0]?.trim() || req.headers.get("x-real-ip") || "unknown";
  return `${prefix}:${ip}`;
}

let lastSweep = 0;
/** 만료 버킷 정리(메모리 누수 방지). 호출 빈도 자체 제한. */
export function sweep(): void {
  const now = Date.now();
  if (now - lastSweep < 60_000) return;
  lastSweep = now;
  for (const [k, b] of buckets) {
    if (now >= b.resetAt) buckets.delete(k);
  }
}
