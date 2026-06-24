// lib/worker/process.ts — 생성 1건 처리 파이프라인 (스펙 §7).
//   processing → 스크래핑 → 코어추출 → 채널 병렬생성 → 저장 → 과금 → done/partial/failed
// [현재: §15.5] 큐/워커 플러밍 + 스크래핑 단계까지. 코어추출/채널생성/과금은 §15.6/7/9에서 채운다.

import { createLogger } from "@/lib/log";
import { scrapeUrls, toSourceRef } from "@/lib/scraper";
import type { GenerationStore, StoredGeneration } from "@/lib/store/types";

const log = createLogger("worker");

export async function processGeneration(store: GenerationStore, rec: StoredGeneration): Promise<void> {
  const t0 = Date.now();
  try {
    log.info("처리 시작", { id: rec.id, keyword: rec.keyword });

    // 2) 스크래핑 — 참고 URL → 본문 텍스트(없으면 "팩트 근거 없음")
    const urls = rec.source_refs.map((r) => r.url).filter(Boolean);
    if (urls.length) {
      const scrapes = await scrapeUrls(urls);
      await store.update(rec.id, { source_refs: scrapes.map(toSourceRef) });
      log.info("스크래핑 완료", { id: rec.id, ok: scrapes.filter((s) => s.ok).length, total: scrapes.length });
    }

    // 3) 코어 추출 — §15.6
    // 4) 채널 병렬 생성 — §15.6(블로그) / §15.7(4채널)
    // 5) 과금 — §15.9

    await store.update(rec.id, { status: "done" });
    log.info("처리 완료", { id: rec.id, ms: Date.now() - t0 });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await store.update(rec.id, { status: "failed", error: message });
    log.error("처리 실패", { id: rec.id, err: message });
  }
}
