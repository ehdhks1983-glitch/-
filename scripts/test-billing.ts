// scripts/test-billing.ts — §16 검증: 과금.
//   · 가입 grant 30 · 생성 완료 시 −10 + tx 1건 + usage_event(ai_cost) · 실패 시 차감 0
//   · 채널 재생성 −2 · 잔액 부족 시 차감 0(음수/이중차감 방지)
// 키리스(인메모리 devWallet)로 동작. 실행: npm run test:billing

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });
process.env.GOMDAERI_MOCK = "1";

import { __resetDevWallet, devWalletSnapshot, getDevWalletBalance } from "@/lib/billing/devWallet";
import { chargePoints } from "@/lib/billing";
import { memoryStore, __resetMemoryStore } from "@/lib/store/memory";
import { drainOnce } from "@/lib/worker/loop";
import { POINTS, SIGNUP_GRANT_POINTS, USAGE_ACTION } from "@/lib/config/points";
import { ALL_CHANNELS, type Channel, type GenOptions } from "@/lib/multipublish/types";

const OPTS: GenOptions = { tone: 50, monetize: false, channels: [...ALL_CHANNELS] };
let fail = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "✅" : "❌"} ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fail++;
}

async function main() {
  // ── 1) 가입 grant ──
  __resetDevWallet();
  check("가입 체험 grant", getDevWalletBalance() === SIGNUP_GRANT_POINTS, `${getDevWalletBalance()}P`);

  // ── 2) 생성 완료 → −10 + tx + usage_event(ai_cost) ──
  __resetMemoryStore();
  const rec = await memoryStore.create({ owner: "u1", keyword: "곰탕", sourceUrls: [], options: OPTS });
  await drainOnce();
  const done = await memoryStore.getById(rec.id);
  check("생성 done", done?.status === "done");
  check("잔액 −10", getDevWalletBalance() === SIGNUP_GRANT_POINTS - POINTS.SET, `${getDevWalletBalance()}P`);
  const snap = devWalletSnapshot();
  const spends = snap.ledger.filter((t) => t.type === "spend");
  check("spend 거래 1건", spends.length === 1);
  check("usage_event ai_cost 기록", snap.usage.length === 1 && snap.usage[0].ai_cost_usd > 0 && snap.usage[0].points_charged === POINTS.SET,
    `ai_cost=$${snap.usage[0]?.ai_cost_usd}`);
  check("usage action=generate_set", snap.usage[0]?.action === USAGE_ACTION.GENERATE_SET);

  // ── 3) 채널 재생성 −2 ──
  const before = getDevWalletBalance();
  const r = await chargePoints({ owner: "u1", points: POINTS.CHANNEL_REGEN, action: USAGE_ACTION.REGEN_CHANNEL, aiCostUsd: 0.0001, ref: rec.id });
  check("재생성 −2", r.ok && getDevWalletBalance() === before - POINTS.CHANNEL_REGEN, `${getDevWalletBalance()}P`);

  // ── 4) 실패 시 차감 0 (모든 채널 무효 → status failed) ──
  __resetDevWallet();
  __resetMemoryStore();
  const failRec = await memoryStore.create({
    owner: "u1",
    keyword: "x",
    sourceUrls: [],
    options: { tone: 50, monetize: false, channels: ["nope1", "nope2"] as unknown as Channel[] },
  });
  await drainOnce();
  const failed = await memoryStore.getById(failRec.id);
  check("status failed(전 채널 실패)", failed?.status === "failed", `status=${failed?.status}`);
  check("실패 시 차감 0", getDevWalletBalance() === SIGNUP_GRANT_POINTS, `${getDevWalletBalance()}P`);

  // ── 5) 잔액 부족 가드(음수/이중차감 방지) ──
  const r2 = await chargePoints({ owner: "u1", points: 9999, action: USAGE_ACTION.GENERATE_SET, aiCostUsd: 0, ref: "x" });
  check("부족 시 ok:false + 차감 0", !r2.ok && getDevWalletBalance() === SIGNUP_GRANT_POINTS, `reason=${r2.reason}`);

  console.log(fail === 0 ? "\n✅ 과금 검증 통과" : `\n❌ ${fail}건 실패`);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("❌ 과금 검증 오류:", e);
  process.exit(1);
});
