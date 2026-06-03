// app/api/leads/route.ts  [신규]
// 공개 페이지의 이메일 신청을 leads 에 저장. IP 기준 rate limit + 이메일 검증.
// RLS 정책상 '게시된 프로젝트'에만 insert 된다.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { collectLead, isValidEmail } from "@/lib/db/leads";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const LEADS_LIMIT = 10; // 분당 신청 횟수(IP 기준)
const LEADS_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "신청 기능이 아직 설정되지 않았어요." }, { status: 503 });
  }

  sweep();
  const rl = rateLimit(clientKey(req, "leads"), LEADS_LIMIT, LEADS_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json({ error: "잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  const projectId = typeof body.projectId === "string" ? body.projectId : "";
  const email = typeof body.email === "string" ? body.email.trim() : "";
  if (!projectId) {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }
  if (!isValidEmail(email)) {
    return NextResponse.json({ error: "이메일 형식을 확인해 주세요." }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServer();
    await collectLead(supabase, projectId, email);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/leads] 실패:", err);
    return NextResponse.json(
      { error: "신청 저장에 실패했어요. 잠시 후 다시 시도해 주세요." },
      { status: 500 },
    );
  }
}
