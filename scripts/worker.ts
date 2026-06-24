// scripts/worker.ts — 독립 워커 프로세스(롱러닝). 실행: npm run worker
// Railway 등에서 웹과 분리해 띄운다(스펙 §3/§4). Supabase 설정 필요(service_role).

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });

import { createLogger } from "@/lib/log";
import { runWorkerLoop, stopWorkerLoop } from "@/lib/worker/loop";

const log = createLogger("worker");
log.info("곰대리 멀티발행 워커 시작");

process.on("SIGINT", () => {
  log.info("SIGINT — 종료 중");
  stopWorkerLoop();
  setTimeout(() => process.exit(0), 500);
});
process.on("SIGTERM", () => {
  stopWorkerLoop();
  setTimeout(() => process.exit(0), 500);
});

runWorkerLoop().catch((err) => {
  log.error("워커 비정상 종료", { err: err instanceof Error ? err.message : String(err) });
  process.exit(1);
});
