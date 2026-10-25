// lib/db/stats.ts  [신규 — 성과 리포트 P1] — 방문 집계·신청 조회(서버 전용, RLS: 소유자만 조회).

import type { SupabaseClient } from "@supabase/supabase-js";
import type { LeadStatRow, StatRow } from "@/lib/analytics/report";
import type { TrafficSource } from "@/lib/analytics/source";

/** 공개 페이지 방문 1회 기록. 게시된 프로젝트만 반영(DB 함수가 확인). */
export async function recordPageView(supabase: SupabaseClient, projectId: string, source: TrafficSource): Promise<void> {
  const { error } = await supabase.rpc("record_page_view", { p_project: projectId, p_source: source });
  if (error) throw new Error(error.message);
}

/** 프로젝트들의 sinceDay(YYYY-MM-DD, KST) 이후 방문 집계. */
export async function selectStats(supabase: SupabaseClient, projectIds: string[], sinceDay: string): Promise<StatRow[]> {
  if (projectIds.length === 0) return [];
  const { data, error } = await supabase
    .from("page_stats")
    .select("project_id, day, source, views")
    .in("project_id", projectIds)
    .gte("day", sinceDay);
  if (error) throw new Error(error.message);
  return (data ?? []) as StatRow[];
}

/** 프로젝트들의 sinceIso 이후 신청(집계용 컬럼만). */
export async function selectLeadStats(supabase: SupabaseClient, projectIds: string[], sinceIso: string): Promise<LeadStatRow[]> {
  if (projectIds.length === 0) return [];
  const { data, error } = await supabase
    .from("leads")
    .select("project_id, created_at, meta")
    .in("project_id", projectIds)
    .gte("created_at", sinceIso);
  if (error) throw new Error(error.message);
  return (data ?? []) as LeadStatRow[];
}
