// lib/worker/loop.ts — 워커 루프. 큐를 폴링하며 잡을 점유→처리(제한 동시성).
// 운영: scripts/worker.ts 가 runWorkerLoop()를 장기 실행(롱러닝 분리, 스펙 §4/§13).
// 개발/검증·in-process kick: drainOnce() 로 큐를 비운다.

import { createLogger } from "@/lib/log";
import { workerStore } from "@/lib/store";
import { processGeneration } from "./process";

const log = createLogger("worker:loop");

function envNum(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
}

export interface WorkerOptions {
  pollMs?: number;
  concurrency?: number;
}

let running = false;

/** 장기 실행 루프. SIGINT 등으로 stopWorkerLoop() 호출 시 종료. */
export async function runWorkerLoop(opts: WorkerOptions = {}): Promise<void> {
  const pollMs = opts.pollMs ?? envNum("WORKER_POLL_MS", 1500);
  const concurrency = opts.concurrency ?? envNum("WORKER_CONCURRENCY", 2);
  const store = workerStore();
  const inFlight = new Set<Promise<void>>();
  running = true;
  log.info("루프 시작", { pollMs, concurrency });

  while (running) {
    try {
      while (inFlight.size < concurrency) {
        const rec = await store.claimNext();
        if (!rec) break;
        const p = processGeneration(store, rec).finally(() => inFlight.delete(p));
        inFlight.add(p);
      }
    } catch (err) {
      log.error("claim 루프 오류", { err: err instanceof Error ? err.message : String(err) });
    }
    if (inFlight.size === 0) await sleep(pollMs);
    else await Promise.race(inFlight);
  }
  await Promise.allSettled(inFlight);
  log.info("루프 종료");
}

export function stopWorkerLoop(): void {
  running = false;
}

/** 큐를 즉시 비운다(테스트/ in-process kick). 처리 건수 반환. */
export async function drainOnce(max = 50): Promise<number> {
  const store = workerStore();
  let n = 0;
  for (; n < max; n++) {
    const rec = await store.claimNext();
    if (!rec) break;
    await processGeneration(store, rec);
  }
  return n;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
