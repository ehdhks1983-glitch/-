// lib/db/supabase.ts  [신규]
// Supabase 설정 + 브라우저 클라이언트. anon 키만 클라이언트에 노출(service_role 금지).
// 서버 전용 클라이언트는 supabase-server.ts(next/headers 의존)에 분리.

import { createBrowserClient } from "@supabase/ssr";

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/** URL+anon 키가 모두 있으면 true. 없으면 인증/저장/게시는 비활성(코어 생성은 계속 동작). */
export function isSupabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

/** 클라이언트 컴포넌트용 브라우저 클라이언트. */
export function createSupabaseBrowser() {
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}
