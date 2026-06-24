// scripts/test-worker.ts — §15.5 검증: 큐/워커 플러밍.
//   · 원자적 점유(claimNext): queued→processing, 중복 점유 없음, 빈 큐=null
//   · 처리 루프(drainOnce): queued→done, 큐 비워짐
// 키리스(인메모리)로 동작. 네트워크/AI 불필요(sourceUrls=[]).
// 실행: npm run test:worker

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });

import { memoryStore, __resetMemoryStore } from "@/lib/store/memory";
import { drainOnce } from "@/lib/worker/loop";
import type { GenOptions } from "@/lib/multipublish/types";

const OPTS: GenOptions = { tone: 50, monetize: false, channels: ["blog"] };
let fail = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "✅" : "❌"} ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fail++;
}

async function main() {
  // ── 1) 원자적 점유 ──
  __resetMemoryStore();
  const a = await memoryStore.create({ owner: "u1", keyword: "곰탕", sourceUrls: [], options: OPTS });
  const b = await memoryStore.create({ owner: "u1", keyword: "삼계탕", sourceUrls: [], options: OPTS });
  check("생성 시 status=queued", a.status === "queued" && b.status === "queued");

  const c1 = await memoryStore.claimNext();
  const c2 = await memoryStore.claimNext();
  const c3 = await memoryStore.claimNext();
  check("claimNext 2건 점유", !!c1 && !!c2 && c1!.id !== c2!.id, `${c1?.id?.slice(0, 8)} / ${c2?.id?.slice(0, 8)}`);
  check("점유 시 processing", c1!.status === "processing" && c2!.status === "processing");
  check("빈 큐 claimNext=null", c3 === null);
  check("FIFO(오래된 것 먼저)", c1!.id === a.id);

  // ── 2) 처리 루프 ──
  __resetMemoryStore();
  await memoryStore.create({ owner: "u1", keyword: "k1", sourceUrls: [], options: OPTS });
  await memoryStore.create({ owner: "u1", keyword: "k2", sourceUrls: [], options: OPTS });
  const processed = await drainOnce();
  check("drainOnce 2건 처리", processed === 2, `처리=${processed}`);

  const list = await memoryStore.listByOwner("u1");
  check("모두 done", list.length === 2 && list.every((g) => g.status === "done"));
  check("처리 후 큐 비어있음", (await memoryStore.claimNext()) === null);

  console.log(fail === 0 ? "\n✅ 워커/큐 검증 통과" : `\n❌ ${fail}건 실패`);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("❌ 워커 검증 오류:", e);
  process.exit(1);
});
