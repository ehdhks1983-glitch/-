// app/dashboard/[projectId]/leads/page.tsx  [신규] — 프로젝트별 신청자 목록(소유자만).
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { selectMyProjectById } from "@/lib/db/projects";
import { selectLeads } from "@/lib/db/leads";

export const dynamic = "force-dynamic";

export default async function LeadsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  if (!isSupabaseConfigured()) redirect("/dashboard");

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const project = await selectMyProjectById(supabase, projectId);
  if (!project) notFound();

  const leads = await selectLeads(supabase, projectId);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <Link href="/dashboard" className="text-sm text-slate-500 hover:text-slate-900">
            ← 대시보드
          </Link>
          <Link
            href={`/s/${project.slug}`}
            target="_blank"
            className="text-sm font-medium text-indigo-600 hover:underline"
          >
            공개 페이지 보기
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-8">
        <h1 className="text-2xl font-bold">{project.title || "제목 없음"} · 신청자</h1>
        <p className="mt-1 text-slate-500">총 {leads.length}명</p>

        {leads.length === 0 ? (
          <p className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-slate-500">
            아직 신청자가 없어요. 공개 페이지를 공유해 보세요.
          </p>
        ) : (
          <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-medium">이메일</th>
                  <th className="px-5 py-3 font-medium">신청 시각</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {leads.map((l) => (
                  <tr key={l.id}>
                    <td className="px-5 py-3">{l.email}</td>
                    <td className="px-5 py-3 text-slate-500">
                      {new Date(l.created_at).toLocaleString("ko-KR")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
