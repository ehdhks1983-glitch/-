// scripts/test-mcp.ts
// MCP 서버 검증: initialize · tools/list · tools/call(문구 검사·인증 오류) · 알림·잘못된 메서드 처리.
// 실행: npm run test:mcp   (키·DB 불필요 — 계정 도구는 인증 오류 경로만 확인)

import assert from "node:assert/strict";
import { handleMessage } from "../lib/mcp/protocol";

const ctx = { origin: "https://example.com", owner: null, admin: null };

let passed = 0;
async function test(name: string, fn: () => Promise<void>) {
  await fn();
  passed++;
  console.log(`✅ ${name}`);
}

type Res = { id: unknown; result?: Record<string, unknown>; error?: { code: number } };
const call = async (method: string, params?: Record<string, unknown>) =>
  (await handleMessage({ jsonrpc: "2.0", id: 1, method, params }, ctx)) as Res | null;
const notify = (method: string) => handleMessage({ jsonrpc: "2.0", method }, ctx);

async function main() {
  await test("initialize: 요청 버전 협상", async () => {
    const r = await call("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t", version: "1" } });
    assert.equal(r?.result?.protocolVersion, "2025-06-18");
    assert.deepEqual(r?.result?.capabilities, { tools: { listChanged: false } });
    const old = await call("initialize", { protocolVersion: "1999-01-01" });
    assert.equal(old?.result?.protocolVersion, "2025-11-25");
  });

  await test("알림은 응답 없음, ping 은 빈 결과", async () => {
    assert.equal(await notify("notifications/initialized"), null);
    assert.deepEqual((await call("ping"))?.result, {});
  });

  await test("tools/list: 5개 도구와 입력 스키마", async () => {
    const tools = (await call("tools/list"))?.result?.tools as { name: string; inputSchema: { type: string } }[];
    assert.deepEqual(
      tools.map((t) => t.name),
      ["check_ad_copy", "get_compliance_rules", "list_pages", "get_page_stats", "create_draft_page"],
    );
    assert.ok(tools.every((t) => t.inputSchema.type === "object"));
  });

  await test("check_ad_copy: 업종 규칙 결과", async () => {
    const r = await call("tools/call", { name: "check_ad_copy", arguments: { text: "면역력 강화에 좋은 수제청", industry: "food" } });
    const data = r?.result?.structuredContent as { can_publish: boolean; findings: { severity: string }[] };
    assert.equal(data.can_publish, false);
    assert.equal(data.findings[0].severity, "block");
    assert.ok(Array.isArray(r?.result?.content));
  });

  await test("계정 도구는 토큰 없으면 isError 결과", async () => {
    const r = await call("tools/call", { name: "list_pages", arguments: {} });
    assert.equal(r?.result?.isError, true);
    const d = await call("tools/call", { name: "create_draft_page", arguments: { description: "동네 빵집" } });
    assert.equal(d?.result?.isError, true);
  });

  await test("잘못된 요청·메서드·도구", async () => {
    assert.equal((await call("resources/list"))?.error?.code, -32601);
    assert.equal((await call("tools/call", { name: "nope" }))?.error?.code, -32602);
    const bad = (await handleMessage({ hello: 1 }, ctx)) as Res;
    assert.equal(bad.error?.code, -32600);
    assert.equal(await handleMessage({ jsonrpc: "2.0", id: 9, result: {} }, ctx), null);
  });

  console.log(`\n${passed}개 통과`);
}

main().catch((err) => {
  console.error("❌", err);
  process.exit(1);
});
