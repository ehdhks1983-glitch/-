// app/api/tokens/[id]/route.ts  [신규 — P2 MCP 연동] — 토큰 폐기(DELETE). 소유자만.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { revokeToken } from "@/lib/db/apiTokens";

export const runtime = "nodejs";

export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!isSupabaseConfigured()) return NextResponse.json({ error: "미설정" }, { status: 503 });
  const { id } = await ctx.params;
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  try {
    const ok = await revokeToken(supabase, id, user.id);
    if (!ok) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/tokens/:id] 폐기 실패:", err);
    return NextResponse.json({ error: "폐기에 실패했어요." }, { status: 500 });
  }
}
