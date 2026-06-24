// app/api/wallet/route.ts — GET 잔액 조회 (스펙 §11). 본인 지갑만.

import { NextResponse } from "next/server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { currentOwner } from "@/lib/auth";
import { getBalance } from "@/lib/billing";

export const runtime = "nodejs";

export async function GET() {
  const { owner, configured } = await currentOwner();
  if (configured && !owner) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  return NextResponse.json({ configured: isSupabaseConfigured(), balance: await getBalance() });
}
