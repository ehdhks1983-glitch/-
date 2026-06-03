// lib/db/supabase-server.ts  [신규] — 서버 전용. next/headers 쿠키에 바인딩.
// next/headers import 자체가 이 모듈을 서버 전용으로 강제한다(클라이언트에서 import 시 빌드 에러).

import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { SUPABASE_ANON_KEY, SUPABASE_URL } from "./supabase";

/** 서버 컴포넌트/route/action 용. 로그인 세션 쿠키에 바인딩. */
export async function createSupabaseServer(): Promise<SupabaseClient> {
  const cookieStore = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // 서버 컴포넌트에서는 쿠키 쓰기 불가 → 미들웨어가 세션을 갱신하므로 무시.
        }
      },
    },
  });
}

/** service_role 키를 쓰는 관리자 클라이언트(서버 전용, RLS 우회). 키 없으면 null. */
export function createSupabaseAdmin(): SupabaseClient | null {
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
  if (!SUPABASE_URL || !serviceKey) return null;
  return createClient(SUPABASE_URL, serviceKey, { auth: { persistSession: false } });
}
