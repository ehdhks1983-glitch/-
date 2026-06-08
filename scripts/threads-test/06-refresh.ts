// scripts/threads-test/06-refresh.ts
// 가상 테스트 7 — 토큰 갱신 스윕(lib/threads/refresh). 실제 네트워크/DB 없이:
//   - 갱신 대상 조회 쿼리(만료 임박 필터)
//   - 새 토큰 저장(updateAccountToken)
//   - 한 계정 실패해도 나머지는 계속 처리(실패 격리)
// 실행: npx tsx scripts/threads-test/06-refresh.ts

import { ok, eq, contains, summary } from "./_assert";
import { installMockFetch, calls, queueResponse } from "./_mockfetch";

process.env.THREADS_APP_ID = "APPID";
process.env.THREADS_APP_SECRET = "SECRET";
process.env.THREADS_REDIRECT_URI = "https://app.example/api/threads/callback";

interface Op {
  method: string;
  args: unknown[];
}

class B {
  ops: Op[] = [];
  constructor(public result: { data?: unknown; error?: unknown }) {}
  private rec(m: string, ...a: unknown[]) {
    this.ops.push({ method: m, args: a });
    return this;
  }
  select(...a: unknown[]) {
    return this.rec("select", ...a);
  }
  update(...a: unknown[]) {
    return this.rec("update", ...a);
  }
  eq(...a: unknown[]) {
    return this.rec("eq", ...a);
  }
  not(...a: unknown[]) {
    return this.rec("not", ...a);
  }
  gt(...a: unknown[]) {
    return this.rec("gt", ...a);
  }
  lte(...a: unknown[]) {
    return this.rec("lte", ...a);
  }
  then(res: (v: unknown) => unknown, rej?: (e: unknown) => unknown) {
    return Promise.resolve(this.result).then(res, rej);
  }
  has(method: string, col?: unknown): boolean {
    return this.ops.some((o) => o.method === method && (col === undefined || o.args[0] === col));
  }
  payload(method: string): Record<string, unknown> {
    const op = this.ops.find((o) => o.method === method);
    return (op?.args[0] as Record<string, unknown>) ?? {};
  }
  findEq(col: string): unknown {
    return this.ops.find((o) => o.method === "eq" && o.args[0] === col)?.args[1];
  }
}

class FakeAdmin {
  builders: B[] = [];
  private queue: { data?: unknown; error?: unknown }[] = [];
  push(r: { data?: unknown; error?: unknown }) {
    this.queue.push(r);
    return this;
  }
  from(_table: string) {
    const b = new B(this.queue.shift() ?? { data: null, error: null });
    this.builders.push(b);
    return b;
  }
}

async function main() {
  const { refreshExpiringTokens } = await import("../../lib/threads/refresh");
  console.log("STEP 7 — lib/threads/refresh.ts (가상 테스트)\n");

  // 시나리오 1: 두 계정 모두 갱신 성공
  installMockFetch();
  const admin = new FakeAdmin();
  admin
    .push({
      data: [
        { id: "a1", threads_user_id: "u1", access_token: "old1", token_expires_at: "2026-06-12T00:00:00Z" },
        { id: "a2", threads_user_id: "u2", access_token: "old2", token_expires_at: "2026-06-13T00:00:00Z" },
      ],
      error: null,
    }) // select
    .push({ data: null, error: null }) // update a1
    .push({ data: null, error: null }); // update a2
  queueResponse({ access_token: "new1", token_type: "bearer", expires_in: 5183944 });
  queueResponse({ access_token: "new2", token_type: "bearer", expires_in: 5183944 });

  const sum = await refreshExpiringTokens(admin as never);
  eq("checked=2", sum.checked, 2);
  eq("refreshed=2", sum.refreshed, 2);
  eq("failed=0", sum.failed, 0);

  // 조회 쿼리: 만료 임박 필터(not null / gt now / lte within)
  const sel = admin.builders[0];
  ok("select: token_expires_at not null", sel.has("not", "token_expires_at"));
  ok("select: token_expires_at > now", sel.has("gt", "token_expires_at"));
  ok("select: token_expires_at <= within", sel.has("lte", "token_expires_at"));

  // 갱신 fetch: refresh 엔드포인트 + 기존 토큰
  contains("refresh1 endpoint", calls[0].url, "/refresh_access_token");
  contains("refresh1 grant", calls[0].url, "grant_type=th_refresh_token");
  contains("refresh1 old token", calls[0].url, "access_token=old1");

  // 새 토큰 저장(update a1): access_token=new1 + 미래 만료시각 + id 가드
  const up1 = admin.builders[1];
  eq("update a1: access_token=new1", up1.payload("update").access_token, "new1");
  eq("update a1: id 가드", up1.findEq("id"), "a1");
  ok("update a1: 만료시각 ISO 저장", typeof up1.payload("update").token_expires_at === "string");
  ok(
    "update a1: 만료시각이 미래",
    new Date(String(up1.payload("update").token_expires_at)).getTime() > Date.now(),
  );
  eq("update a2: access_token=new2", admin.builders[2].payload("update").access_token, "new2");

  // 시나리오 2: 갱신 실패 격리(한 계정 실패 → failed=1, 업데이트 호출 안 함)
  installMockFetch();
  const admin2 = new FakeAdmin();
  admin2.push({
    data: [{ id: "bad", threads_user_id: "u", access_token: "expired", token_expires_at: "2026-06-12T00:00:00Z" }],
    error: null,
  });
  queueResponse({ error: { message: "token expired, cannot refresh" } }, 400);

  const sum2 = await refreshExpiringTokens(admin2 as never);
  eq("실패: checked=1", sum2.checked, 1);
  eq("실패: refreshed=0", sum2.refreshed, 0);
  eq("실패: failed=1", sum2.failed, 1);
  eq("실패 시 update 호출 안 함(빌더 1개=select만)", admin2.builders.length, 1);

  summary("STEP 7 — refresh.ts");
}

main().catch((err) => {
  console.error("❌ 테스트 실행 오류:", err);
  process.exit(1);
});
