// app/api/tokens/route.ts  [신규 — P2 MCP 연동]
// 개인 액세스 토큰 발급(POST). 로그인 필요. 원문 토큰은 이 응답에서 한 번만 보여 준다.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { issueToken, selectMyTokens } from "@/lib/db/apiTokens";

export const runtime = "nodejs";

const MAX_ACTIVE_TOKENS = 5;

export async function POST(req: Request) {
  if (!isSupabaseConfigured()) return NextResponse.json({ error: "미설정" }, { status: 503 });
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const name = typeof body.name === "string" && body.name.trim() ? body.name.trim() : "AI 비서";

  try {
    const active = (await selectMyTokens(supabase, user.id)).filter((t) => !t.revoked_at);
    if (active.length >= MAX_ACTIVE_TOKENS) {
      return NextResponse.json({ error: `토큰은 최대 ${MAX_ACTIVE_TOKENS}개까지 쓸 수 있어요. 안 쓰는 토큰을 먼저 폐기해 주세요.` }, { status: 400 });
    }
    const { token, row } = await issueToken(supabase, user.id, name);
    return NextResponse.json({ token, row });
  } catch (err) {
    console.error("[api/tokens] 발급 실패:", err);
    return NextResponse.json({ error: "발급에 실패했어요. 잠시 후 다시 시도해 주세요." }, { status: 500 });
  }
}
