// proxy.ts  [Next.js 16: Middleware → Proxy 리네임. 구 middleware.ts 대체.]
// 매 요청마다 Supabase 세션 쿠키 갱신(@supabase/ssr 권장 패턴) + 워크스페이스 보호.
// Supabase 미설정 시 즉시 통과(no-op) → 키 없이도 앱이 정상 동작(키리스 개발/검증).

import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { SUPABASE_ANON_KEY, SUPABASE_URL, isSupabaseConfigured } from "@/lib/db/supabase";

/** 로그인이 필요한 경로(스펙 §11: 본인 리소스만). API 라우트는 자체 401 처리. */
const PROTECTED_PREFIXES = ["/workspace"];

export async function proxy(req: NextRequest) {
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
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = req.nextUrl.pathname;
  const needsAuth = PROTECTED_PREFIXES.some((p) => path === p || path.startsWith(p + "/"));
  if (needsAuth && !user) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("redirect", path);
    return NextResponse.redirect(url);
  }

  return res;
}

export const config = {
  // 정적 자산/이미지 제외한 모든 경로에서 세션 갱신.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
