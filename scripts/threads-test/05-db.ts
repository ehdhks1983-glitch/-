// scripts/threads-test/05-db.ts
// 가상 테스트 5 — 데이터 계층(lib/threads/db). 실제 Supabase 없이, 체인 호출을 기록하는 가짜 클라이언트로
// 쿼리 구성(컬럼/필터/가드)을 검증한다. 보안 핵심: UI용 조회엔 access_token 이 빠져야 한다.
// 실행: npx tsx scripts/threads-test/05-db.ts

import { ok, eq, contains, summary } from "./_assert";
import type { SupabaseClient } from "@supabase/supabase-js";
import * as db from "../../lib/threads/db";

interface Op {
  method: string;
  args: unknown[];
}

class FakeBuilder {
  ops: Op[] = [];
  constructor(
    public table: string,
    public result: { data?: unknown; error?: unknown; count?: number },
  ) {}
  private rec(m: string, ...args: unknown[]) {
    this.ops.push({ method: m, args });
    return this;
  }
  select(...a: unknown[]) {
    return this.rec("select", ...a);
  }
  insert(...a: unknown[]) {
    return this.rec("insert", ...a);
  }
  update(...a: unknown[]) {
    return this.rec("update", ...a);
  }
  upsert(...a: unknown[]) {
    return this.rec("upsert", ...a);
  }
  delete(...a: unknown[]) {
    return this.rec("delete", ...a);
  }
  eq(...a: unknown[]) {
    return this.rec("eq", ...a);
  }
  lte(...a: unknown[]) {
    return this.rec("lte", ...a);
  }
  gte(...a: unknown[]) {
    return this.rec("gte", ...a);
  }
  order(...a: unknown[]) {
    return this.rec("order", ...a);
  }
  limit(...a: unknown[]) {
    return this.rec("limit", ...a);
  }
  maybeSingle() {
    this.rec("maybeSingle");
    return Promise.resolve(this.result);
  }
  single() {
    this.rec("single");
    return Promise.resolve(this.result);
  }
  // single 없이 await 하는 체인(목록/카운트/due)을 위해 thenable.
  then(res: (v: unknown) => unknown, rej?: (e: unknown) => unknown) {
    return Promise.resolve(this.result).then(res, rej);
  }
  selectCols(): string {
    const op = this.ops.find((o) => o.method === "select");
    return op ? String(op.args[0] ?? "") : "";
  }
  findEq(col: string): unknown {
    const op = this.ops.find((o) => o.method === "eq" && o.args[0] === col);
    return op ? op.args[1] : undefined;
  }
  payload(method: string): Record<string, unknown> {
    const op = this.ops.find((o) => o.method === method);
    return (op?.args[0] as Record<string, unknown>) ?? {};
  }
}

class FakeSupabase {
  last: FakeBuilder | null = null;
  next: { data?: unknown; error?: unknown; count?: number } = { data: null, error: null };
  setNext(r: { data?: unknown; error?: unknown; count?: number }) {
    this.next = r;
  }
  from(table: string) {
    const b = new FakeBuilder(table, this.next);
    this.last = b;
    return b;
  }
}

function client(fake: FakeSupabase): SupabaseClient {
  return fake as unknown as SupabaseClient;
}

async function main() {
  console.log("STEP 5 — lib/threads/db.ts (가상 테스트)\n");
  const fake = new FakeSupabase();

  // 1) getMyAccount — 토큰 제외(보안)
  fake.setNext({ data: { id: "a1", threads_user_id: "u", username: "n", token_expires_at: null, created_at: "t" }, error: null });
  const acc = await db.getMyAccount(client(fake), "owner1");
  ok("getMyAccount: access_token 컬럼 미포함", !fake.last!.selectCols().includes("access_token"));
  contains("getMyAccount: 공개 컬럼 select", fake.last!.selectCols(), "username");
  eq("getMyAccount: owner 필터", fake.last!.findEq("owner"), "owner1");
  ok("getMyAccount: 결과 매핑", acc?.id === "a1");

  // 2) getMyAccountWithToken — 토큰 포함(서버 발행용)
  fake.setNext({ data: { id: "a1", threads_user_id: "u", username: "n", token_expires_at: null, created_at: "t", access_token: "secret" }, error: null });
  const accT = await db.getMyAccountWithToken(client(fake), "owner1");
  ok("getMyAccountWithToken: access_token 포함", fake.last!.selectCols().includes("access_token"));
  ok("withToken: 토큰 값 반환", accT?.access_token === "secret");

  // 3) getMyAccount null
  fake.setNext({ data: null, error: null });
  const none = await db.getMyAccount(client(fake), "owner1");
  ok("계정 없으면 null", none === null);

  // 4) 에러 전파
  fake.setNext({ data: null, error: { message: "db boom" } });
  let dbErr = "";
  try {
    await db.getMyAccount(client(fake), "owner1");
  } catch (e) {
    dbErr = e instanceof Error ? e.message : String(e);
  }
  contains("DB 에러 전파", dbErr, "db boom");

  // 5) upsertAccount — 토큰 저장 + onConflict owner + 반환은 공개 컬럼
  fake.setNext({ data: { id: "a1", threads_user_id: "u", username: "n", token_expires_at: null, created_at: "t" }, error: null });
  await db.upsertAccount(client(fake), "owner1", {
    threadsUserId: "u",
    username: "n",
    accessToken: "LONGTOKEN",
    tokenExpiresAt: null,
  });
  ok("upsert: access_token 저장됨", fake.last!.payload("upsert").access_token === "LONGTOKEN");
  ok("upsert: onConflict=owner", (fake.last!.ops.find((o) => o.method === "upsert")?.args[1] as { onConflict?: string })?.onConflict === "owner");
  ok("upsert: 반환 select 는 토큰 제외", !fake.last!.selectCols().includes("access_token"));

  // 6) insertPost — owner/account_id/status 세팅
  fake.setNext({ data: { id: "p1" }, error: null });
  await db.insertPost(client(fake), "owner1", {
    accountId: "a1",
    text: "글",
    mediaType: "TEXT",
    status: "scheduled",
    scheduledAt: "2030-01-01T00:00:00.000Z",
  });
  const ins = fake.last!.payload("insert");
  eq("insert owner", ins.owner, "owner1");
  eq("insert account_id", ins.account_id, "a1");
  eq("insert status", ins.status, "scheduled");
  eq("insert scheduled_at", ins.scheduled_at, "2030-01-01T00:00:00.000Z");

  // 7) selectMyPosts — owner 필터 + 최신순
  fake.setNext({ data: [{ id: "p1" }, { id: "p2" }], error: null });
  const posts = await db.selectMyPosts(client(fake), "owner1");
  eq("selectMyPosts owner 필터", fake.last!.findEq("owner"), "owner1");
  ok("selectMyPosts order 호출", fake.last!.ops.some((o) => o.method === "order"));
  eq("selectMyPosts 결과 수", posts.length, 2);

  // 8) claimForPublish — scheduled→publishing 원자적 가드
  fake.setNext({ data: { id: "p1" }, error: null });
  const claimed = await db.claimForPublish(client(fake), "p1");
  ok("claim: status=publishing 로 update", fake.last!.payload("update").status === "publishing");
  eq("claim: id 가드", fake.last!.findEq("id"), "p1");
  eq("claim: status=scheduled 가드(중복발행 방지)", fake.last!.findEq("status"), "scheduled");
  ok("claim: 성공 true", claimed === true);

  // 이미 누가 가져간 경우(행 없음) → false
  fake.setNext({ data: null, error: null });
  const claimed2 = await db.claimForPublish(client(fake), "p1");
  ok("claim: 행 없으면 false", claimed2 === false);

  // 9) markPublished — 상태/미디어id/published_at 세팅
  fake.setNext({ data: null, error: null });
  await db.markPublished(client(fake), "p1", "MEDIA_X");
  const mp = fake.last!.payload("update");
  eq("markPublished status", mp.status, "published");
  eq("markPublished media id", mp.threads_media_id, "MEDIA_X");
  ok("markPublished published_at 설정", typeof mp.published_at === "string");

  // 10) markFailed — 메시지 500자 제한
  fake.setNext({ data: null, error: null });
  await db.markFailed(client(fake), "p1", "x".repeat(900));
  const mf = fake.last!.payload("update");
  eq("markFailed status", mf.status, "failed");
  ok("markFailed error <= 500자", String(mf.error).length <= 500);

  // 11) countPublishedSince — count/head + published 필터
  fake.setNext({ count: 3, error: null });
  const n = await db.countPublishedSince(client(fake), "a1", "2020-01-01T00:00:00Z");
  const selOpt = fake.last!.ops.find((o) => o.method === "select")?.args[1] as { count?: string; head?: boolean };
  ok("count: head=true", selOpt?.head === true);
  eq("count: status=published 필터", fake.last!.findEq("status"), "published");
  ok("count: published_at gte", fake.last!.ops.some((o) => o.method === "gte"));
  eq("count 결과", n, 3);

  // 12) getDuePosts — 임베드 account(토큰 포함) + scheduled + lte
  fake.setNext({ data: [{ id: "p1", account: { id: "a1", threads_user_id: "u", access_token: "t" } }], error: null });
  const due = await db.getDuePosts(client(fake), "2030-01-01T00:00:00Z", 20);
  contains("due: account 임베드", fake.last!.selectCols(), "account:threads_accounts");
  contains("due: 토큰 포함(서버 발행용)", fake.last!.selectCols(), "access_token");
  eq("due: status=scheduled", fake.last!.findEq("status"), "scheduled");
  ok("due: scheduled_at lte", fake.last!.ops.some((o) => o.method === "lte"));
  ok("due: limit 적용", fake.last!.ops.some((o) => o.method === "limit"));
  eq("due 결과 수", due.length, 1);

  summary("STEP 5 — db.ts");
}

main().catch((err) => {
  console.error("❌ 테스트 실행 오류:", err);
  process.exit(1);
});
