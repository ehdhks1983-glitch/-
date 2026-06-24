// lib/billing/index.ts — 잔액 조회 + 원자적 차감(spend).
//   키리스: 인메모리 devWallet · Supabase: spend_points/wallet_balance RPC(원자적, §12 동시성).
//   차감/usage_event 기록은 한 트랜잭션(Supabase RPC) — §12.3.

import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseAdmin, createSupabaseServer } from "@/lib/db/supabase-server";
import { createLogger } from "@/lib/log";
import { devSpend, getDevWalletBalance } from "./devWallet";

const log = createLogger("billing");

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
    log.error("잔액 조회 실패", { err: error.message });
    return 0;
  }
  return typeof data === "number" ? data : 0;
}

export interface ChargeArgs {
  owner: string;
  points: number;
  action: string;
  aiCostUsd: number;
  ref?: string;
  metadata?: Record<string, unknown>;
}

export interface ChargeResult {
  ok: boolean;
  balance?: number;
  reason?: string;
}

/**
 * 원자적 차감: 잔액 −points + point_transactions(spend) + usage_events(ai_cost) 한 트랜잭션(§12.3).
 * 잔액 부족이면 ok:false(차감 0). 음수/이중차감 방지는 Postgres 함수의 balance>=cost 가드 / 인메모리 원자성.
 * 워커(service_role) 또는 재생성 라우트에서 호출. 사용자 세션과 무관하게 owner 명시.
 */
export async function chargePoints(a: ChargeArgs): Promise<ChargeResult> {
  if (a.points <= 0) return { ok: true };

  if (!isSupabaseConfigured()) {
    const r = devSpend({ points: a.points, action: a.action, aiCostUsd: a.aiCostUsd, ref: a.ref });
    return { ok: r.ok, balance: r.balance, reason: r.ok ? undefined : "insufficient_points" };
  }

  const admin = createSupabaseAdmin();
  if (!admin) {
    log.error("service_role 미설정 — 과금 불가");
    return { ok: false, reason: "no_admin" };
  }
  const { data, error } = await admin.rpc("spend_points", {
    p_user_id: a.owner,
    p_points: a.points,
    p_action: a.action,
    p_ai_cost: a.aiCostUsd,
    p_product_code: "multipublish",
    p_ref: a.ref ?? null,
    p_metadata: a.metadata ?? {},
  });
  if (error) {
    const insufficient = /insufficient_points/.test(error.message);
    if (!insufficient) log.error("spend 실패", { err: error.message });
    return { ok: false, reason: insufficient ? "insufficient_points" : error.message };
  }
  return { ok: true, balance: typeof data === "number" ? data : undefined };
}
