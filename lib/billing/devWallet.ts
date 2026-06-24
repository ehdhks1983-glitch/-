// lib/billing/devWallet.ts
// 키리스(Supabase 미설정) 개발/검증 모드용 인메모리 지갑. 단일 프로세스 가정.
// Supabase가 설정되면 이 모듈은 쓰이지 않고 Postgres 함수(spend_points/grant_points)가 진실이 된다.
// §15.9(과금)에서 spend/grant 원자 처리를 사용한다. 여기서는 잔액 캐시 + 단순 원장.

import { SIGNUP_GRANT_POINTS, TX_TYPE } from "@/lib/config/points";

interface DevTx {
  type: string;
  amount: number;
  balance_after: number;
  ref?: string;
  at: string;
}

interface DevUsage {
  action: string;
  points_charged: number;
  ai_cost_usd: number;
  at: string;
}

let balance = SIGNUP_GRANT_POINTS;
let initialized = false;
const ledger: DevTx[] = [];
const usage: DevUsage[] = [];

function ensureInit() {
  if (initialized) return;
  initialized = true;
  ledger.push({
    type: TX_TYPE.GRANT,
    amount: SIGNUP_GRANT_POINTS,
    balance_after: balance,
    ref: "signup_trial",
    at: new Date().toISOString(),
  });
}

export function getDevWalletBalance(): number {
  ensureInit();
  return balance;
}

/** 원자적 차감(단일 프로세스). 잔액 부족이면 ok:false, 잔액 변동 없음. */
export function devSpend(args: {
  points: number;
  action: string;
  aiCostUsd: number;
  ref?: string;
}): { ok: boolean; balance: number } {
  ensureInit();
  if (balance < args.points) return { ok: false, balance };
  balance -= args.points;
  ledger.push({
    type: TX_TYPE.SPEND,
    amount: -args.points,
    balance_after: balance,
    ref: args.ref,
    at: new Date().toISOString(),
  });
  usage.push({
    action: args.action,
    points_charged: args.points,
    ai_cost_usd: args.aiCostUsd,
    at: new Date().toISOString(),
  });
  return { ok: true, balance };
}

export function devGrant(points: number): number {
  ensureInit();
  balance += points;
  ledger.push({
    type: TX_TYPE.GRANT,
    amount: points,
    balance_after: balance,
    at: new Date().toISOString(),
  });
  return balance;
}

/** 디버그/검증용 스냅샷. */
export function devWalletSnapshot() {
  ensureInit();
  return { balance, ledger: [...ledger], usage: [...usage] };
}
