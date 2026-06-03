// app/dashboard/page.tsx  [신규] — 내 프로젝트 목록(서버 컴포넌트).
import Link from "next/link";
import { redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { selectMyProjects } from "@/lib/db/projects";
import LogoutButton from "@/components/LogoutButton";
import DeleteProjectButton from "@/components/DeleteProjectButton";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  if (!isSupabaseConfigured()) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">설정이 필요해요</h1>
        <p className="mt-2 text-slate-600">
          Supabase 환경변수를 설정하면 로그인·저장·게시를 쓸 수 있어요. 그 전에도 페이지 생성과
          미리보기는 그대로 동작합니다.
        </p>
        <Link href="/project/new" className="mt-6 inline-block rounded-full bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white">
          페이지 만들러 가기
        </Link>
      </Centered>
    );
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const projects = await selectMyProjects(supabase);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-5 py-4">
          <Link href="/" className="font-bold tracking-tight">
            Prompt<span className="text-indigo-600">Site</span>
          </Link>
          <div className="flex items-center gap-2">
            <LogoutButton />
            <Link
              href="/project/new"
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500"
            >
              + 새 페이지
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-5 py-8">
        <h1 className="text-2xl font-bold">내 페이지</h1>
        {projects.length === 0 ? (
          <p className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-slate-500">
            아직 만든 페이지가 없어요. “+ 새 페이지”로 시작해 보세요.
          </p>
        ) : (
          <ul className="mt-6 space-y-3">
            {projects.map((p) => (
              <li key={p.id} className="rounded-xl border border-slate-200 bg-white p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="font-semibold">{p.title || "제목 없음"}</h2>
                      {p.published && (
                        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          게시중
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-slate-400">/s/{p.slug}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-sm">
                    <Link
                      href={`/project/${p.id}`}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium transition hover:bg-slate-50"
                    >
                      편집
                    </Link>
                    <Link
                      href={`/s/${p.slug}`}
                      target="_blank"
                      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium transition hover:bg-slate-50"
                    >
                      공개 페이지
                    </Link>
                    <Link
                      href={`/dashboard/${p.id}/leads`}
                      className="rounded-lg bg-slate-900 px-3 py-1.5 font-medium text-white transition hover:bg-slate-700"
                    >
                      신청자
                    </Link>
                    <DeleteProjectButton projectId={p.id} />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
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
