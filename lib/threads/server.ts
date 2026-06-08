// lib/threads/server.ts  [신규] — Threads 라우트 공통 가드(서버 전용).
// Supabase/Threads 설정 + 로그인 확인을 한 곳에서. 실패 시 그대로 반환할 NextResponse 를 돌려준다.

import { NextResponse } from "next/server";
import type { SupabaseClient, User } from "@supabase/supabase-js";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { isThreadsConfigured } from "./config";

export interface Authed {
  supabase: SupabaseClient;
  user: User;
}

/**
 * 공통 가드. requireThreads=true 면 Threads 연동 키까지 확인한다.
 * 통과하면 { supabase, user }, 아니면 적절한 상태코드의 NextResponse 를 반환.
 */
export async function requireThreadsUser(
  opts: { requireThreads?: boolean } = {},
): Promise<Authed | NextResponse> {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "로그인/저장 기능이 설정되지 않았어요." }, { status: 503 });
  }
  if (opts.requireThreads && !isThreadsConfigured()) {
    return NextResponse.json({ error: "Threads 연동이 설정되지 않았어요." }, { status: 503 });
  }
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  return { supabase, user };
}

/** 타입 가드: 가드 통과(=인증됨) 여부. */
export function isAuthed(v: Authed | NextResponse): v is Authed {
  return v instanceof NextResponse === false;
}
