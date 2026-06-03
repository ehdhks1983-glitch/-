// middleware.ts  [신규]
// Supabase 세션 쿠키를 매 요청마다 갱신(@supabase/ssr 권장 패턴).
// Supabase 미설정 시 즉시 통과(no-op) → 키 없이도 앱이 정상 동작.

import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { SUPABASE_ANON_KEY, SUPABASE_URL, isSupabaseConfigured } from "@/lib/db/supabase";

export async function middleware(req: NextRequest) {
  if (!isSupabaseConfigured()) return NextResponse.next();

  let res = NextResponse.next({ request: req });

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return req.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => req.cookies.set(name, value));
        res = NextResponse.next({ request: req });
        cookiesToSet.forEach(({ name, value, options }) => res.cookies.set(name, value, options));
      },
    },
  });

  // getUser() 호출이 만료 토큰을 갱신하고 setAll 로 쿠키를 다시 심는다.
  await supabase.auth.getUser();
  return res;
}

export const config = {
  // 정적 자산/이미지 제외한 모든 경로에서 세션 갱신.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
