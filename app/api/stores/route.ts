// app/api/stores/route.ts  [신규 — P2 여러 매장] — 매장 추가(POST). 로그인 필요.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { insertStore, selectMyStores } from "@/lib/db/stores";

export const runtime = "nodejs";

const MAX_STORES = 50;

export async function POST(req: Request) {
  if (!isSupabaseConfigured()) return NextResponse.json({ error: "매장 기능이 아직 설정되지 않았어요." }, { status: 503 });
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name) return NextResponse.json({ error: "매장 이름을 입력해 주세요." }, { status: 400 });

  try {
    if ((await selectMyStores(supabase, user.id)).length >= MAX_STORES) {
      return NextResponse.json({ error: `매장은 최대 ${MAX_STORES}개까지 만들 수 있어요.` }, { status: 400 });
    }
    const store = await insertStore(supabase, user.id, name);
    return NextResponse.json({ store });
  } catch (err) {
    console.error("[api/stores] 추가 실패:", err);
    return NextResponse.json({ error: "매장 추가에 실패했어요." }, { status: 500 });
  }
}
