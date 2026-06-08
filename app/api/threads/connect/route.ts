// app/api/threads/connect/route.ts  [신규]
// Threads 계정 연결 시작점. 로그인 필요. CSRF 방지 state 를 쿠키에 심고 Meta OAuth 인가 페이지로 리다이렉트.

import { NextResponse } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import { buildAuthorizeUrl, THREADS_STATE_COOKIE, THREADS_STATE_TTL_SEC } from "@/lib/threads/config";

export const runtime = "nodejs";

export async function GET() {
  const ctx = await requireThreadsUser({ requireThreads: true });
  if (!isAuthed(ctx)) return ctx;

  const state = crypto.randomUUID();
  const res = NextResponse.redirect(buildAuthorizeUrl(state));
  res.cookies.set(THREADS_STATE_COOKIE, state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: THREADS_STATE_TTL_SEC,
  });
  return res;
}
