// scripts/threads-test/03-drafts.ts
// 가상 테스트 3 — AI 초안 생성(lib/threads/generateDrafts). PROMPTSITE_MOCK=1 로 강제 목 모드 →
// 실제 AI 호출 없이 개수 제한/길이 제한/주제 반영을 검증한다.
// 실행: npx tsx scripts/threads-test/03-drafts.ts

import { ok, eq, summary } from "./_assert";

// core.isMockMode 가 호출 시점에 읽으므로 import 전에 강제 목 모드로.
process.env.PROMPTSITE_MOCK = "1";

async function main() {
  const { generateThreadDrafts } = await import("../../lib/threads/generateDrafts");
  const { THREADS_MAX_TEXT, THREADS_MAX_DRAFTS } = await import("../../lib/threads/config");

  console.log("STEP 3 — lib/threads/generateDrafts.ts (가상 테스트, 목 모드)\n");

  const topic = "동네 카페 운영";
  const d3 = await generateThreadDrafts({ topic, count: 3 });
  eq("요청 3개 → 3개", d3.length, 3);
  ok("각 초안에 주제 반영", d3.every((s) => s.includes(topic)));
  ok("각 초안 비어있지 않음", d3.every((s) => s.trim().length > 0));
  ok(`각 초안 길이 <= ${THREADS_MAX_TEXT}`, d3.every((s) => s.length <= THREADS_MAX_TEXT));

  const high = await generateThreadDrafts({ topic: "x", count: 99 });
  ok(`count 99 → 최대 ${THREADS_MAX_DRAFTS}로 제한`, high.length >= 1 && high.length <= THREADS_MAX_DRAFTS);

  const low = await generateThreadDrafts({ topic: "x", count: 0 });
  eq("count 0 → 최소 1", low.length, 1);

  const en = await generateThreadDrafts({ topic: "side project", count: 2, language: "en" });
  eq("영어 2개", en.length, 2);
  ok("영어 초안에 주제 반영", en.every((s) => s.includes("side project")));

  summary("STEP 3 — generateDrafts.ts");
}

main().catch((err) => {
  console.error("❌ 테스트 실행 오류:", err);
  process.exit(1);
});
