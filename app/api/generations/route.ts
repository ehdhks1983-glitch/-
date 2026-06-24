// app/api/generations/route.ts — POST 생성 요청 (스펙 §11).
//   잔액 체크(≥ SET) → job 생성(queued) → 워커 kick → { generationId }
//   완료 시 차감(spend)은 워커에서(§12.3, §15.9). 여기선 사전 잔액 확인만.

import { NextResponse } from "next/server";
import { currentOwner } from "@/lib/auth";
import { getBalance } from "@/lib/billing";
import { POINTS } from "@/lib/config/points";
import { createLogger } from "@/lib/log";
import { ALL_CHANNELS, type Channel, type GenOptions } from "@/lib/multipublish/types";
import { toSummary } from "@/lib/multipublish/serialize";
import { clientKey, rateLimit, sweep } from "@/lib/rateLimit";
import { requestStore } from "@/lib/store";
import { kickWorker } from "@/lib/worker/kick";

export const runtime = "nodejs";

const log = createLogger("api/generations");
const RETENTION_DAYS = Number(process.env.GENERATION_RETENTION_DAYS) || 90;

interface CreateBody {
  keyword?: unknown;
  sourceUrls?: unknown;
  options?: { tone?: unknown; monetize?: unknown; channels?: unknown };
}

/** GET /api/generations — 내 발행물 목록 (스펙 §11). 본인 것만, 최신순. */
export async function GET() {
  const { owner, configured } = await currentOwner();
  if (configured && !owner) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  try {
    const store = await requestStore();
    const items = await store.listByOwner(owner as string, 100);
    return NextResponse.json({ generations: items.map(toSummary) });
  } catch (err) {
    log.error("목록 조회 실패", { err: err instanceof Error ? err.message : String(err) });
    return NextResponse.json({ error: "목록 조회에 실패했어요." }, { status: 500 });
  }
}

export async function POST(req: Request) {
  sweep();
  const rl = rateLimit(clientKey(req, "gen"), 20, 60_000);
  if (!rl.ok) return NextResponse.json({ error: "요청이 많아요. 잠시 후 다시 시도해 주세요." }, { status: 429 });

  const { owner, configured } = await currentOwner();
  if (configured && !owner) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  let body: CreateBody;
  try {
    body = (await req.json()) as CreateBody;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  const keyword = typeof body.keyword === "string" ? body.keyword.trim() : "";
  if (!keyword) return NextResponse.json({ error: "키워드를 입력해 주세요." }, { status: 400 });
  if (keyword.length > 200) return NextResponse.json({ error: "키워드가 너무 길어요." }, { status: 400 });

  const sourceUrls = normalizeUrls(body.sourceUrls);
  const options = normalizeOptions(body.options);

  // 잔액 체크(스펙 §12.2): 부족하면 차단(충전 유도).
  const balance = await getBalance();
  if (balance < POINTS.SET) {
    return NextResponse.json(
      { error: `크레딧이 부족해요. (보유 ${balance}P / 필요 ${POINTS.SET}P)`, code: "insufficient_points", balance },
      { status: 402 },
    );
  }

  try {
    const store = await requestStore();
    const rec = await store.create({
      owner: owner as string,
      keyword,
      title: keyword,
      sourceUrls,
      options,
      expiresAt: new Date(Date.now() + RETENTION_DAYS * 86_400_000).toISOString(),
    });
    kickWorker(); // 키리스/inline: 즉시 처리 / Supabase: 별도 워커가 처리
    log.info("생성 요청", { id: rec.id, owner, channels: options.channels.length });
    return NextResponse.json({ generationId: rec.id }, { status: 201 });
  } catch (err) {
    log.error("생성 요청 실패", { err: err instanceof Error ? err.message : String(err) });
    return NextResponse.json({ error: "생성 요청에 실패했어요." }, { status: 500 });
  }
}

function normalizeUrls(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const item of v) {
    if (typeof item !== "string") continue;
    const s = item.trim();
    if (!s) continue;
    try {
      const u = new URL(s);
      if ((u.protocol === "http:" || u.protocol === "https:") && !out.includes(s)) out.push(s);
    } catch {
      /* 잘못된 URL 무시 */
    }
    if (out.length >= 5) break;
  }
  return out;
}

function normalizeOptions(o: CreateBody["options"]): GenOptions {
  const toneRaw = Number(o?.tone);
  const tone = Number.isFinite(toneRaw) ? Math.min(100, Math.max(0, Math.round(toneRaw))) : 50;
  const monetize = o?.monetize === true;
  const requested = Array.isArray(o?.channels) ? (o!.channels as unknown[]) : [];
  const channels = ALL_CHANNELS.filter((c) => requested.includes(c)) as Channel[];
  return { tone, monetize, channels: channels.length ? channels : [...ALL_CHANNELS] };
}
