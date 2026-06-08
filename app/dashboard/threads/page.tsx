// app/dashboard/threads/page.tsx  [신규] — Threads 자동발행 콘솔(서버 컴포넌트).
// 로그인/계정/큐를 서버에서 로드해 클라이언트 매니저에 전달. 토큰은 전달하지 않는다.

import Link from "next/link";
import { redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import {
  isThreadsConfigured,
  THREADS_DAILY_CAP,
  THREADS_META_DAILY_LIMIT,
  THREADS_MAX_TEXT,
} from "@/lib/threads/config";
import { getMyAccount, selectMyPosts, countPublishedLast24h } from "@/lib/threads/db";
import ThreadsManager from "@/components/threads/ThreadsManager";
import LogoutButton from "@/components/LogoutButton";

export const dynamic = "force-dynamic";

type SP = Record<string, string | string[] | undefined>;

export default async function ThreadsPage({ searchParams }: { searchParams: Promise<SP> }) {
  if (!isSupabaseConfigured()) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">설정이 필요해요</h1>
        <p className="mt-2 text-slate-600">
          로그인·저장 기능에는 Supabase 환경변수가 필요해요. README의 Supabase 설정을 참고하세요.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-full bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white"
        >
          홈으로
        </Link>
      </Centered>
    );
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const sp = await searchParams;
  const notice =
    typeof sp.connected === "string"
      ? "connected"
      : typeof sp.error === "string"
        ? `error:${sp.error}`
        : null;

  const threadsReady = isThreadsConfigured();
  const account = threadsReady ? await getMyAccount(supabase, user.id) : null;
  const posts = threadsReady ? await selectMyPosts(supabase, user.id) : [];

  let publishedToday = 0;
  if (account) {
    publishedToday = await countPublishedLast24h(supabase, account.id);
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <Link href="/" className="font-bold tracking-tight">
            Prompt<span className="text-indigo-600">Site</span>
          </Link>
          <div className="flex items-center gap-2 text-sm">
            <Link
              href="/dashboard"
              className="rounded-full border border-slate-200 px-3 py-1.5 font-medium transition hover:bg-slate-50"
            >
              내 페이지
            </Link>
            <LogoutButton />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-8">
        <h1 className="text-2xl font-bold">🧵 Threads 자동발행</h1>
        <p className="mt-1 text-sm text-slate-500">
          공식 Threads API로 <b>내 계정에</b> 글을 예약/발행해요. 검토 후 발행하는 구조라 안전합니다.
        </p>

        {!threadsReady && (
          <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
            <p className="font-semibold">Threads 연동 키가 아직 없어요.</p>
            <p className="mt-1">
              Meta 개발자 앱을 만들고 아래 환경변수를 <code>.env.local</code>(또는 Vercel)에 넣으면 연결 버튼이 활성화돼요.
            </p>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-amber-100/70 px-3 py-2 text-xs">
              THREADS_APP_ID=…{"\n"}THREADS_APP_SECRET=…{"\n"}THREADS_REDIRECT_URI=https://내도메인/api/threads/callback
            </pre>
            <p className="mt-2">설정 방법은 README의 “Threads 자동발행” 절을 참고하세요. (키 없이도 아래 초안 생성은 체험 가능)</p>
          </div>
        )}

        <div className="mt-6">
          <ThreadsManager
            threadsReady={threadsReady}
            maxText={THREADS_MAX_TEXT}
            dailyCap={THREADS_DAILY_CAP}
            metaDailyLimit={THREADS_META_DAILY_LIMIT}
            initialAccount={
              account
                ? {
                    username: account.username,
                    threads_user_id: account.threads_user_id,
                    token_expires_at: account.token_expires_at,
                  }
                : null
            }
            initialPosts={posts}
            publishedToday={publishedToday}
            notice={notice}
          />
        </div>
      </main>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
      <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center">{children}</div>
    </div>
  );
}
