// app/api/stores/[id]/route.ts  [신규 — P2 여러 매장] — 매장 삭제(DELETE). 소속 페이지는 '매장 미지정'으로 남는다.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { deleteStore } from "@/lib/db/stores";

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
    await deleteStore(supabase, id, user.id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/stores/:id] 삭제 실패:", err);
    return NextResponse.json({ error: "삭제에 실패했어요." }, { status: 500 });
  }
}
