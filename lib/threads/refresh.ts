// lib/threads/refresh.ts  [신규] — 만료 임박 장기 토큰 갱신 스윕(서버/크론 전용).
// 크론이 매 실행마다 호출. 만료 7일(THREADS_REFRESH_BEFORE_DAYS) 이내 토큰만 갱신 →
// 갱신되면 +60일로 창 밖으로 빠지므로 계정당 사실상 ~53일에 1회만 갱신(낭비 없음).
// 갱신 실패(만료/폐기 등)는 로그만 남기고 넘어간다(해당 계정은 재연결 필요).

import type { SupabaseClient } from "@supabase/supabase-js";
import { refreshLongLivedToken } from "./client";
import { getAccountsNeedingRefresh, updateAccountToken } from "./db";
import { THREADS_REFRESH_BEFORE_DAYS } from "./config";

export interface RefreshSummary {
  checked: number;
  refreshed: number;
  failed: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;

export async function refreshExpiringTokens(admin: SupabaseClient): Promise<RefreshSummary> {
  const now = Date.now();
  const nowIso = new Date(now).toISOString();
  const withinIso = new Date(now + THREADS_REFRESH_BEFORE_DAYS * DAY_MS).toISOString();

  const accounts = await getAccountsNeedingRefresh(admin, withinIso, nowIso);
  let refreshed = 0;
  let failed = 0;

  for (const a of accounts) {
    try {
      const fresh = await refreshLongLivedToken(a.access_token);
      const expiresAt =
        fresh.expiresInSec > 0 ? new Date(Date.now() + fresh.expiresInSec * 1000).toISOString() : null;
      await updateAccountToken(admin, a.id, fresh.accessToken, expiresAt);
      refreshed++;
    } catch (err) {
      failed++;
      console.error(
        `[threads/refresh] 토큰 갱신 실패 account=${a.id}:`,
        err instanceof Error ? err.message : err,
      );
    }
  }

  return { checked: accounts.length, refreshed, failed };
}
