// app/api/threads/drafts/route.ts  [신규]
// POST { topic, tone?, count?, language? } → AI 초안 N개 생성(저장 안 함). 사용자가 검토 후 /posts 로 저장/예약.
// AI 호출이라 IP 기준 rate limit + maxDuration. Threads 연결 전이라도 초안은 만들 수 있음(연결은 저장 단계에서 필요).

import { NextResponse } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";
import { generateThreadDrafts } from "@/lib/threads/generateDrafts";

export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_TOPIC = 1000;
const DRAFTS_LIMIT = 12; // 분당 생성 횟수(IP 기준) — 토큰 비용 폭주 방지
const DRAFTS_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  const ctx = await requireThreadsUser();
  if (!isAuthed(ctx)) return ctx;

  sweep();
  const rl = rateLimit(clientKey(req, "threads-drafts"), DRAFTS_LIMIT, DRAFTS_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json({ error: "요청이 많아요. 잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }

  const topic = typeof body.topic === "string" ? body.topic.trim() : "";
  if (!topic) return NextResponse.json({ error: "어떤 주제로 쓸지 적어 주세요." }, { status: 400 });
  if (topic.length > MAX_TOPIC) {
    return NextResponse.json({ error: `주제가 너무 깁니다. ${MAX_TOPIC}자 이하로 줄여 주세요.` }, { status: 400 });
  }

  const tone = typeof body.tone === "string" ? body.tone : undefined;
  const count = typeof body.count === "number" ? body.count : undefined;
  const language = body.language === "en" ? "en" : "ko";

  try {
    const drafts = await generateThreadDrafts({ topic, tone, count, language });
    return NextResponse.json({ drafts });
  } catch (err) {
    console.error("[api/threads/drafts] 생성 실패:", err);
    return NextResponse.json(
      { error: "초안 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
