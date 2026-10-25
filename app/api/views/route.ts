// app/api/views/route.ts  [신규 — 성과 리포트 P1]
// 공개 페이지 방문 1회 기록(유입 경로 분류값만). 봇은 무시, IP 기준 rate limit.
// 실패해도 방문자 화면에는 영향이 없도록 항상 204 로 응답한다.

import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { recordPageView } from "@/lib/db/stats";
import { isTrafficSource } from "@/lib/analytics/source";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const VIEWS_LIMIT = 60; // 분당 기록 횟수(IP 기준)
const VIEWS_WINDOW_MS = 60_000;
const BOT_UA = /bot|crawl|spider|slurp|preview|facebookexternalhit|kakaotalk-scrap|yeti|headless/i;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function POST(req: Request) {
  const done = new Response(null, { status: 204 });
  if (!isSupabaseConfigured()) return done;
  if (BOT_UA.test(req.headers.get("user-agent") ?? "")) return done;

  sweep();
  if (!rateLimit(clientKey(req, "views"), VIEWS_LIMIT, VIEWS_WINDOW_MS).ok) return done;

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return done;
  }
  const projectId = typeof body.projectId === "string" ? body.projectId : "";
  if (!UUID_RE.test(projectId)) return done;

  try {
    const supabase = await createSupabaseServer();
    await recordPageView(supabase, projectId, isTrafficSource(body.source) ? body.source : "other");
  } catch (err) {
    console.error("[api/views] 기록 실패:", err);
  }
  return done;
}
