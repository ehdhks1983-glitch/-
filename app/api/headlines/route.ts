// app/api/headlines/route.ts  [신규]
// 한 줄 아이디어 → 히어로 헤드라인 후보 N개. /api/discover 의 검증·rate-limit·에러 패턴을 그대로 따른다.

import { NextResponse } from "next/server";
import { suggestHeadlines, MAX_HEADLINES } from "@/lib/ai/suggestHeadlines";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_IDEA = 300;
const HEADLINES_LIMIT = 12; // 분당 후보 생성 횟수(IP 기준)
const HEADLINES_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  sweep();
  const rl = rateLimit(clientKey(req, "headlines"), HEADLINES_LIMIT, HEADLINES_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json({ error: "요청이 많아요. 잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return bad("요청 형식이 올바르지 않습니다.");
  }

  const ideaRaw = body.idea;
  if (typeof ideaRaw !== "string" || !ideaRaw.trim()) {
    return bad("헤드라인을 뽑을 아이디어가 필요해요.");
  }
  if (ideaRaw.length > MAX_IDEA) {
    return bad(`아이디어가 너무 깁니다. ${MAX_IDEA}자 이하로 줄여 주세요.`);
  }

  try {
    const headlines = await suggestHeadlines(ideaRaw.trim(), MAX_HEADLINES);
    if (headlines.length === 0) {
      return NextResponse.json(
        { error: "헤드라인 후보를 만들지 못했어요. 잠시 후 다시 시도해 주세요." },
        { status: 422 },
      );
    }
    return NextResponse.json({ headlines });
  } catch (err) {
    console.error("[api/headlines] 실패:", err);
    return NextResponse.json(
      { error: "후보 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}

function bad(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}
