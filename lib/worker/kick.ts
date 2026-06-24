// lib/worker/kick.ts — 생성 요청 후 워커를 깨운다.
//   키리스(인메모리) 또는 WORKER_INLINE=1: 같은 프로세스에서 비동기 drain(응답 안 막음).
//   Supabase 운영: no-op — 별도 워커 프로세스(npm run worker)가 큐를 처리(롱러닝 분리, 스펙 §4).

import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createLogger } from "@/lib/log";
import { drainOnce } from "./loop";

const log = createLogger("worker:kick");
let draining = false;

export function kickWorker(): void {
  const inline = !isSupabaseConfigured() || process.env.WORKER_INLINE === "1";
  if (!inline || draining) return;
  draining = true;
  // fire-and-forget: 큐가 빌 때까지 1건씩 처리. 요청 응답을 막지 않는다.
  void (async () => {
    try {
      while ((await drainOnce(1)) > 0) {
        /* keep draining */
      }
    } catch (err) {
      log.error("kick drain 실패", { err: err instanceof Error ? err.message : String(err) });
    } finally {
      draining = false;
    }
  })();
}
