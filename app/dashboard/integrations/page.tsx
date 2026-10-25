// app/dashboard/integrations/page.tsx  [신규 — P2 MCP 연동]
// AI 비서(ChatGPT·Claude 등) 연동: 개인 액세스 토큰 관리 + MCP 연결 방법. 로그인 필요.

import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { selectMyTokens, type ApiTokenRow } from "@/lib/db/apiTokens";
import TokenManager from "@/components/TokenManager";

export const dynamic = "force-dynamic";

export default async function IntegrationsPage() {
  if (!isSupabaseConfigured()) redirect("/dashboard");

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  let tokens: ApiTokenRow[] = [];
  let needsMigration = false;
  try {
    tokens = await selectMyTokens(supabase, user.id);
  } catch (err) {
    console.error("[integrations] 토큰 조회 실패:", err);
    needsMigration = true;
  }

  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const endpoint = `${proto}://${host}/api/mcp`;
  const adminReady = Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <Link href="/dashboard" className="text-sm text-slate-500 hover:text-slate-900">
            ← 대시보드
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-8">
        <h1 className="text-2xl font-bold">AI 비서 연동</h1>
        <p className="mt-1 text-sm text-slate-500">
          ChatGPT·Claude 같은 AI 비서가 MCP 로 연결해 문구 검사, 성과 조회, 초안 만들기를 할 수 있어요.
        </p>

        {needsMigration && (
          <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            토큰 정보를 불러오지 못했어요. Supabase SQL Editor 에서 database/schema.sql 을 다시 실행해 주세요.
          </p>
        )}
        {!adminReady && (
          <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            서버에 SUPABASE_SERVICE_ROLE_KEY 가 없어 지금은 토큰 없이 쓰는 문구 검사·규칙 조회만 동작해요.
          </p>
        )}

        <div className="mt-6">
          <TokenManager tokens={tokens} endpoint={endpoint} />
        </div>
      </main>
    </div>
  );
}
