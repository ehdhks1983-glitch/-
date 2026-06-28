// app/admin/licenses/page.tsx  [신규] — 통합 라이선스 관리(서버 컴포넌트, 관리자 전용).
// 게이트: 미설정 안내 / 비로그인 → /login / 비관리자 → 403 안내.

import Link from "next/link";
import { redirect } from "next/navigation";
import { createSupabaseAdmin, createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { isAdminEmail, isLicenseAdminConfigured } from "@/lib/license/admin";
import { listLicenses } from "@/lib/license/db";
import { bots } from "@/lib/license/config";
import LicenseManager from "@/components/license/LicenseManager";

export const dynamic = "force-dynamic";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        {children}
      </div>
    </div>
  );
}

export default async function LicenseAdminPage() {
  if (!isSupabaseConfigured() || !isLicenseAdminConfigured()) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">설정이 필요해요</h1>
        <p className="mt-3 text-left text-sm leading-relaxed text-slate-600">
          통합 라이선스 관리를 켜려면 다음이 필요합니다:
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-left text-sm text-slate-600">
          <li>
            <code className="rounded bg-slate-100 px-1">NEXT_PUBLIC_SUPABASE_URL</code> /{" "}
            <code className="rounded bg-slate-100 px-1">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>
          </li>
          <li>
            <code className="rounded bg-slate-100 px-1">SUPABASE_SERVICE_ROLE_KEY</code> (서버 전용)
          </li>
          <li>
            <code className="rounded bg-slate-100 px-1">LICENSE_ADMIN_EMAILS</code> (관리자 이메일)
          </li>
        </ul>
        <p className="mt-4 text-left text-xs text-slate-500">
          그리고 <code className="rounded bg-slate-100 px-1">database/license-schema.sql</code> 을
          Supabase SQL Editor 에서 실행하세요.
        </p>
      </Centered>
    );
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  if (!isAdminEmail(user.email)) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">접근 권한이 없어요</h1>
        <p className="mt-3 text-sm text-slate-600">
          이 계정({user.email})은 라이선스 관리자가 아닙니다.
        </p>
        <Link href="/" className="mt-6 inline-block rounded-full bg-slate-800 px-6 py-2.5 text-sm font-semibold text-white">
          홈으로
        </Link>
      </Centered>
    );
  }

  const admin = createSupabaseAdmin()!;
  const licenses = await listLicenses(admin);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <div className="font-bold tracking-tight">
            통합 라이선스 <span className="text-indigo-600">관리</span>
          </div>
          <span className="text-sm text-slate-500">{user.email}</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-8">
        <LicenseManager initialLicenses={licenses} botList={bots()} />
      </main>
    </div>
  );
}
