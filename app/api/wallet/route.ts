// app/api/wallet/route.ts — GET 잔액 조회 (스펙 §11). 본인 지갑만.
// 키리스(미설정) 모드: 인메모리 지갑(§15.9에서 연동)까지는 체험 grant 기본값을 반환.

import { NextResponse } from "next/server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { SIGNUP_GRANT_POINTS } from "@/lib/config/points";
import { getDevWalletBalance } from "@/lib/billing/devWallet";

export const runtime = "nodejs";

export async function GET() {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ configured: false, balance: getDevWalletBalance() });
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  const { data, error } = await supabase.rpc("wallet_balance", { p_user_id: user.id });
  if (error) {
    console.error("[api/wallet] 잔액 조회 실패:", error.message);
    return NextResponse.json({ error: "잔액 조회에 실패했어요." }, { status: 500 });
  }
  return NextResponse.json({
    configured: true,
    balance: typeof data === "number" ? data : SIGNUP_GRANT_POINTS,
  });
}
