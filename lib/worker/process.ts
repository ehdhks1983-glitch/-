// lib/worker/process.ts — 생성 1건 처리 파이프라인 (스펙 §7).
//   processing → 스크래핑 → 코어추출(Haiku) → 채널 병렬생성 → 저장 → (과금 §15.9) → done/partial/failed
// 과금(spend + usage_event)은 §15.9에서 연결. 지금은 산출물별 ai_cost 저장 + 총원가 로깅.

import { createLogger } from "@/lib/log";
import { scrapeUrls, toSourceRef } from "@/lib/scraper";
import { extractCore } from "@/lib/pipeline/core";
import { generateChannel } from "@/lib/pipeline/channels";
import { ALL_CHANNELS, type Channel, type GenerationStatus } from "@/lib/multipublish/types";
import type { GenerationStore, StoredGeneration } from "@/lib/store/types";

const log = createLogger("worker");

export async function processGeneration(store: GenerationStore, rec: StoredGeneration): Promise<void> {
  const t0 = Date.now();
  let totalAiCost = 0;
  try {
    log.info("처리 시작", { id: rec.id, keyword: rec.keyword });

    // 2) 스크래핑 — 본문 텍스트는 메모리 보관(코어 입력), 메타만 영속화.
    const urls = rec.source_refs.map((r) => r.url).filter(Boolean);
    let sources: { url: string; text: string }[] = [];
    if (urls.length) {
      const scrapes = await scrapeUrls(urls);
      await store.update(rec.id, { source_refs: scrapes.map(toSourceRef) });
      sources = scrapes.filter((s) => s.ok && s.text).map((s) => ({ url: s.url, text: s.text }));
      log.info("스크래핑 완료", { id: rec.id, ok: sources.length, total: scrapes.length });
    }

    // 3) 코어 추출
    const coreRes = await extractCore({ keyword: rec.keyword, options: rec.options, sources });
    totalAiCost += coreRes.costUsd;
    await store.update(rec.id, { core: coreRes.core });
    log.info("코어 추출 완료", { id: rec.id, facts: coreRes.core.facts.length, mocked: coreRes.mocked });

    // 4) 채널 병렬 생성 (블로그 Sonnet + 4채널 Haiku — §15.7에서 4채널 추가)
    const channels = rec.options.channels?.length ? rec.options.channels : ALL_CHANNELS;
    const ctx = { keyword: rec.keyword, options: rec.options };
    const results = await Promise.allSettled(channels.map((ch) => generateChannel(ch, coreRes.core, ctx)));

    let okCount = 0;
    let failCount = 0;
    let blogTitle = "";
    for (let i = 0; i < channels.length; i++) {
      const ch: Channel = channels[i];
      const r = results[i];
      if (r.status === "fulfilled") {
        totalAiCost += r.value.costUsd;
        await store.addOutput(rec.id, {
          channel: ch,
          status: "done",
          content: r.value.content,
          ai_cost_usd: r.value.costUsd,
        });
        if (ch === "blog") blogTitle = (r.value.content as { title?: string })?.title ?? "";
        okCount++;
      } else {
        await store.addOutput(rec.id, {
          channel: ch,
          status: "failed",
          content: {},
          ai_cost_usd: 0,
          error: r.reason instanceof Error ? r.reason.message : String(r.reason),
        });
        failCount++;
        log.warn("채널 생성 실패", { id: rec.id, channel: ch, err: String(r.reason) });
      }
    }

    // 5) 과금 — §15.9 (지금은 총원가 로깅만)
    const status: GenerationStatus = failCount === 0 ? "done" : okCount === 0 ? "failed" : "partial";
    await store.update(rec.id, {
      status,
      title: rec.title || blogTitle || rec.keyword,
      error: status === "failed" ? "모든 채널 생성 실패" : null,
    });
    log.info("처리 완료", { id: rec.id, status, okCount, failCount, aiCostUsd: round6(totalAiCost), ms: Date.now() - t0 });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await store.update(rec.id, { status: "failed", error: message });
    log.error("처리 실패", { id: rec.id, err: message });
  }
}

function round6(n: number): number {
  return Math.round(n * 1e6) / 1e6;
}
