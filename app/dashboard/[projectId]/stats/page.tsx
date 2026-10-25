// app/dashboard/[projectId]/stats/page.tsx  [신규 — 성과 리포트 P1]
// 프로젝트 성과: 최근 30일 방문·신청·전환율, 일별 방문(14일), 유입 경로별 방문·신청·전환율. 소유자만.
// 지표를 '만든 페이지 수'가 아니라 방문→신청으로 보여 준다(보고서 P1 '성과 지표 변경').

import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { selectMyProjectById } from "@/lib/db/projects";
import { selectLeadStats, selectStats } from "@/lib/db/stats";
import { buildReport, lastDays, leadsSinceIso, type LeadStatRow, type StatRow } from "@/lib/analytics/report";
import ShareLinks from "@/components/ShareLinks";
import StatsReport from "@/components/StatsReport";

export const dynamic = "force-dynamic";

const REPORT_DAYS = 30;
const CHART_DAYS = 14;

export default async function StatsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  if (!isSupabaseConfigured()) redirect("/dashboard");

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const project = await selectMyProjectById(supabase, projectId, user.id);
  if (!project) notFound();

  const since = lastDays(REPORT_DAYS)[0];
  let stats: StatRow[] = [];
  let leads: LeadStatRow[] = [];
  let needsMigration = false;
  try {
    [stats, leads] = await Promise.all([
      selectStats(supabase, [projectId], since),
      selectLeadStats(supabase, [projectId], leadsSinceIso(REPORT_DAYS)),
    ]);
  } catch (err) {
    console.error("[stats] 조회 실패:", err);
    needsMigration = true;
  }

  const report = buildReport(stats, leads, REPORT_DAYS);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <Link href="/dashboard" className="text-sm text-slate-500 hover:text-slate-900">
            ← 대시보드
          </Link>
          <Link href={`/dashboard/${project.id}/leads`} className="text-sm font-medium text-indigo-600 hover:underline">
            신청자 보기
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-8">
        <h1 className="text-2xl font-bold">{project.title || "제목 없음"} · 성과</h1>
        <p className="mt-1 text-sm text-slate-500">최근 {REPORT_DAYS}일 · 한국 시간 기준</p>

        {needsMigration && (
          <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            성과 데이터를 불러오지 못했어요. Supabase SQL Editor 에서 database/schema.sql 을 다시 실행해 주세요.
          </p>
        )}

        <StatsReport report={report} chartDays={CHART_DAYS} />

        {/* 채널별 공유 링크 */}
        <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="font-semibold">채널별 공유 링크</h2>
          <p className="mt-1 text-sm text-slate-500">
            채널마다 다른 링크를 올리면 어디서 손님이 왔는지 정확히 집계돼요.
          </p>
          <div className="mt-4">
            <ShareLinks slug={project.slug} />
          </div>
        </section>

        <p className="mt-6 text-xs leading-5 text-slate-400">
          같은 탭에서 새로고침한 방문은 한 번으로 셉니다. 검색봇·링크 미리보기는 제외하며, IP 등 개인정보는 저장하지 않습니다.
        </p>
      </main>
    </div>
  );
}
