// lib/billing/index.ts — 잔액 조회(읽기). 차감/지급(spend/grant)은 §15.9에서 추가.
//   키리스: 인메모리 devWallet · Supabase: wallet_balance RPC(본인).

import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { getDevWalletBalance } from "./devWallet";

/** 현재 사용자(세션) 잔액. 키리스는 dev 지갑. 미로그인(설정됨)이면 0. */
export async function getBalance(): Promise<number> {
  if (!isSupabaseConfigured()) return getDevWalletBalance();
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return 0;
  const { data, error } = await supabase.rpc("wallet_balance", { p_user_id: user.id });
  if (error) {
    console.error("[billing] 잔액 조회 실패:", error.message);
    return 0;
  }
  return typeof data === "number" ? data : 0;
}
