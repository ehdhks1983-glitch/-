// app/api/generations/[id]/channels/[ch]/regenerate/route.ts — POST 채널 재생성 (스펙 §11).
//   코어 재사용(편집된 코어 허용) → 해당 채널만 1회 생성(인라인, 단일 Haiku 호출) → 새 variant 추가.
//   차감(2P)은 §15.9에서 연결. 여기선 사전 잔액 확인.

import { NextResponse } from "next/server";
import { currentOwner } from "@/lib/auth";
import { getBalance } from "@/lib/billing";
import { POINTS } from "@/lib/config/points";
import { createLogger } from "@/lib/log";
import { generateChannel } from "@/lib/pipeline/channels";
import { strList, sanitizeLine } from "@/lib/pipeline/sanitize";
import { ALL_CHANNELS, type Channel, type Core } from "@/lib/multipublish/types";
import { clientKey, rateLimit, sweep } from "@/lib/rateLimit";
import { requestStore, workerStore } from "@/lib/store";

export const runtime = "nodejs";
const log = createLogger("api/regenerate");

type Ctx = { params: Promise<{ id: string; ch: string }> };

export async function POST(req: Request, ctx: Ctx) {
  sweep();
  const { id, ch } = await ctx.params;
  if (!ALL_CHANNELS.includes(ch as Channel)) {
    return NextResponse.json({ error: "알 수 없는 채널이에요." }, { status: 400 });
  }
  const channel = ch as Channel;

  const rl = rateLimit(clientKey(req, "regen"), 30, 60_000);
  if (!rl.ok) return NextResponse.json({ error: "요청이 많아요. 잠시 후 다시 시도해 주세요." }, { status: 429 });

  const { owner, configured } = await currentOwner();
  if (configured && !owner) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  const reqStore = await requestStore();
  const rec = await reqStore.getById(id, owner ?? undefined);
  if (!rec) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
  if (!rec.core) return NextResponse.json({ error: "코어가 아직 준비되지 않았어요." }, { status: 400 });

  // 편집된 코어(선택) 반영 — 메시지/앵글/대상/톤/태그만, facts는 출처 보존 위해 유지.
  let core = rec.core;
  try {
    const body = (await req.json()) as { core?: Partial<Core> };
    if (body?.core && typeof body.core === "object") {
      core = mergeEditedCore(rec.core, body.core);
      await workerStore().update(id, { core });
    }
  } catch {
    /* 본문 없음/파싱 실패 → 기존 코어 사용 */
  }

  // 잔액 체크(차감은 §15.9).
  const balance = await getBalance();
  if (balance < POINTS.CHANNEL_REGEN) {
    return NextResponse.json(
      { error: `크레딧이 부족해요. (보유 ${balance}P / 필요 ${POINTS.CHANNEL_REGEN}P)`, code: "insufficient_points", balance },
      { status: 402 },
    );
  }

  try {
    const result = await generateChannel(channel, core, {
      keyword: rec.keyword,
      options: rec.options,
      regenerate: true,
    });
    const variant_no = await workerStore().addOutput(id, {
      channel,
      status: "done",
      content: result.content,
      ai_cost_usd: result.costUsd,
    });
    log.info("채널 재생성", { id, channel, variant_no });
    return NextResponse.json({ channel, variant_no, content: result.content });
  } catch (err) {
    log.error("채널 재생성 실패", { id, channel, err: err instanceof Error ? err.message : String(err) });
    return NextResponse.json({ error: "재생성에 실패했어요. 다시 시도해 주세요." }, { status: 500 });
  }
}

/** 편집 가능한 코어 필드만 병합(facts는 출처 무결성 위해 기존 유지). */
function mergeEditedCore(base: Core, edited: Partial<Core>): Core {
  return {
    core_message: sanitizeLine(edited.core_message, 300) || base.core_message,
    angles: Array.isArray(edited.angles) && edited.angles.length ? strList(edited.angles, 8, 200) : base.angles,
    facts: base.facts,
    target_reader: sanitizeLine(edited.target_reader, 200) || base.target_reader,
    tone: sanitizeLine(edited.tone, 120) || base.tone,
    tag_candidates:
      Array.isArray(edited.tag_candidates) && edited.tag_candidates.length
        ? strList(edited.tag_candidates, 15, 30)
        : base.tag_candidates,
  };
}
