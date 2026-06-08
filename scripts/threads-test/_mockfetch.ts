// scripts/threads-test/_mockfetch.ts — 전역 fetch를 목으로 대체. 실제 네트워크 호출 없이
// 요청(url/method/body)을 기록하고, 미리 큐에 넣은 응답을 순서대로 돌려준다.

export interface Call {
  url: string;
  method: string;
  body: string;
}

export const calls: Call[] = [];
let queue: { status: number; body: string }[] = [];

/** 다음 fetch가 돌려줄 응답을 큐에 추가(여러 번 호출하면 순서대로 소비). */
export function queueResponse(body: unknown, status = 200): void {
  queue.push({ status, body: typeof body === "string" ? body : JSON.stringify(body) });
}

/** 목 fetch 설치 + 상태 초기화. */
export function installMockFetch(): void {
  calls.length = 0;
  queue = [];
  globalThis.fetch = (async (input: unknown, init?: { method?: string; body?: unknown }) => {
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: init?.body != null ? String(init.body) : "",
    });
    const next = queue.shift() ?? { status: 200, body: "{}" };
    return new Response(next.body, { status: next.status });
  }) as unknown as typeof fetch;
}
