// app/api/threads/account/route.ts  [신규]
// GET: 연결 상태 + 오늘(24h) 발행 건수/한도. (토큰은 절대 반환하지 않음)
// DELETE: 계정 연결 해제.

import { NextResponse } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import { getMyAccount, deleteAccount, countPublishedSince } from "@/lib/threads/db";
import { THREADS_DAILY_CAP, THREADS_META_DAILY_LIMIT } from "@/lib/threads/config";

export const runtime = "nodejs";

export async function GET() {
  const ctx = await requireThreadsUser();
  if (!isAuthed(ctx)) return ctx;
  const { supabase, user } = ctx;

  try {
    const account = await getMyAccount(supabase, user.id);
    let publishedToday = 0;
    if (account) {
      const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      // 소유자 세션도 RLS 안에서 자기 행만 카운트 → account.id 로 안전하게 집계.
      publishedToday = await countPublishedSince(supabase, account.id, since);
    }
    return NextResponse.json({
      connected: Boolean(account),
      account: account
        ? {
            username: account.username,
            threads_user_id: account.threads_user_id,
            token_expires_at: account.token_expires_at,
          }
        : null,
      dailyCap: THREADS_DAILY_CAP,
      metaDailyLimit: THREADS_META_DAILY_LIMIT,
      publishedToday,
    });
  } catch (err) {
    console.error("[api/threads/account] GET 실패:", err);
    return NextResponse.json({ error: "상태를 불러오지 못했어요." }, { status: 500 });
  }
}

export async function DELETE() {
  const ctx = await requireThreadsUser();
  if (!isAuthed(ctx)) return ctx;
  const { supabase, user } = ctx;

  try {
    await deleteAccount(supabase, user.id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/threads/account] DELETE 실패:", err);
    return NextResponse.json({ error: "연결 해제에 실패했어요." }, { status: 500 });
  }
}
