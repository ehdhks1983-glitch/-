// app/workspace/layout.tsx — 워크스페이스 셸: 상단바 + 좌측 레일 + 메인 (스펙 §10).
// 서버 컴포넌트: 세션에서 계정 이메일을 읽어 상단바에 전달. 미로그인(설정됨)이면 /login.

import { redirect } from "next/navigation";
import Topbar from "@/components/shell/Topbar";
import LeftRail from "@/components/shell/LeftRail";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";

export default async function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const configured = isSupabaseConfigured();
  let email: string | null = null;

  if (configured) {
    const supabase = await createSupabaseServer();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) redirect("/login?redirect=/workspace");
    email = user.email ?? null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Topbar email={email} configured={configured} />
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col sm:flex-row">
        <LeftRail />
        <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
