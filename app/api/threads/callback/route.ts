// app/api/threads/callback/route.ts  [신규]
// Meta OAuth 콜백. state 대조(CSRF) → 코드 교환(단기→장기 토큰) → 프로필 조회 → 계정 저장 → 대시보드로.
// 실패는 사용자 친화 메시지로만(코드/토큰 노출 금지). 토큰은 DB(RLS owner-only)에만 저장.

import { NextResponse, type NextRequest } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import { THREADS_STATE_COOKIE } from "@/lib/threads/config";
import {
  exchangeCodeForToken,
  exchangeForLongLivedToken,
  getProfile,
} from "@/lib/threads/client";
import { upsertAccount } from "@/lib/threads/db";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const ctx = await requireThreadsUser({ requireThreads: true });
  if (!isAuthed(ctx)) return ctx;
  const { supabase, user } = ctx;

  const url = req.nextUrl;
  const back = (params: Record<string, string>) =>
    NextResponse.redirect(buildBack(url.origin, params));

  // 사용자가 권한 거부했거나 Meta 가 에러를 돌려준 경우
  const oauthError = url.searchParams.get("error");
  if (oauthError) {
    return clearState(back({ error: "denied" }));
  }

  const code = url.searchParams.get("code") ?? "";
  const state = url.searchParams.get("state") ?? "";
  const savedState = req.cookies.get(THREADS_STATE_COOKIE)?.value ?? "";

  if (!code || !state || !savedState || state !== savedState) {
    return clearState(back({ error: "state" }));
  }

  try {
    const short = await exchangeCodeForToken(code);
    const long = await exchangeForLongLivedToken(short.accessToken);
    const profile = await getProfile(short.userId, long.accessToken);

    const expiresAt =
      long.expiresInSec > 0
        ? new Date(Date.now() + long.expiresInSec * 1000).toISOString()
        : null;

    await upsertAccount(supabase, user.id, {
      threadsUserId: short.userId,
      username: profile.username,
      accessToken: long.accessToken,
      tokenExpiresAt: expiresAt,
    });

    return clearState(back({ connected: "1" }));
  } catch (err) {
    console.error("[api/threads/callback] 연결 실패:", err);
    return clearState(back({ error: "exchange" }));
  }
}

/** state 쿠키 제거(1회용). */
function clearState(res: NextResponse): NextResponse {
  res.cookies.set(THREADS_STATE_COOKIE, "", { path: "/", maxAge: 0 });
  return res;
}

function buildBack(origin: string, params: Record<string, string>): URL {
  const u = new URL("/dashboard/threads", origin);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  return u;
}
