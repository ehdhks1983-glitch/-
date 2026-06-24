// scripts/test-gateway.ts — §16 검증: 게이트웨이 단독 호출 시 텍스트 + 토큰 + costUsd 반환.
// 실행: npm run test:gateway  (키 없으면 자동 목 모드)

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });

import { generate, isMockMode } from "@/lib/gateway";
import { computeCostUsd, tierForTask, type GatewayTask } from "@/lib/config/models";

const CASES: { task: GatewayTask; expectTier: "haiku" | "sonnet" }[] = [
  { task: "core", expectTier: "haiku" },
  { task: "blog", expectTier: "sonnet" },
  { task: "channel.threads", expectTier: "haiku" },
  { task: "channel.instagram", expectTier: "haiku" },
  { task: "channel.cafe", expectTier: "haiku" },
  { task: "channel.shorts", expectTier: "haiku" },
  { task: "factcheck", expectTier: "haiku" },
];

async function main() {
  console.log(`게이트웨이 검증 (mock=${isMockMode()})\n`);
  let failures = 0;

  for (const c of CASES) {
    const r = await generate({
      task: c.task,
      system: "너는 테스트용 어시스턴트다. JSON 한 줄로 답하라.",
      input: `task=${c.task} 에 대한 짧은 샘플`,
      mock: JSON.stringify({ ok: true, task: c.task }),
    });

    const tier = tierForTask(c.task);
    const expectedCost = computeCostUsd(tier, r.usage.inputTokens, r.usage.outputTokens);
    const checks = [
      ["text 존재", r.text.length > 0],
      ["inputTokens>0", r.usage.inputTokens > 0],
      ["outputTokens>0", r.usage.outputTokens > 0],
      ["costUsd 일치", Math.abs(r.costUsd - expectedCost) < 1e-12],
      ["티어 매핑", tier === c.expectTier && r.tier === c.expectTier],
    ] as const;

    const ok = checks.every(([, v]) => v);
    if (!ok) failures++;
    console.log(
      `${ok ? "✅" : "❌"} ${c.task.padEnd(18)} tier=${r.tier.padEnd(6)} model=${r.model.padEnd(22)} ` +
        `tok=${r.usage.inputTokens}/${r.usage.outputTokens} cost=$${r.costUsd.toFixed(8)}`,
    );
    if (!ok) console.log("   실패 체크:", checks.filter(([, v]) => !v).map(([k]) => k).join(", "));
  }

  // 캐시 동작: cacheable 동일 입력 2회 → 2번째는 cached(비용 0)
  const a = await generate({ task: "core", system: "S", input: "동일입력", cacheable: true, mock: "{}" });
  const b = await generate({ task: "core", system: "S", input: "동일입력", cacheable: true, mock: "{}" });
  const cacheOk = !a.cached && b.cached && b.costUsd === 0;
  console.log(`${cacheOk ? "✅" : "❌"} 응답 캐시: 1차 cached=${a.cached} / 2차 cached=${b.cached}(cost=$${b.costUsd})`);
  if (!cacheOk) failures++;

  console.log(failures === 0 ? "\n✅ 게이트웨이 검증 통과" : `\n❌ ${failures}건 실패`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error("❌ 게이트웨이 검증 오류:", err);
  process.exit(1);
});
