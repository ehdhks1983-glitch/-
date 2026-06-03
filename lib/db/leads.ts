// lib/db/leads.ts  [신규] — 서버 전용 리드(신청자) 쿼리 헬퍼.

import type { SupabaseClient } from "@supabase/supabase-js";

export interface LeadRow {
  id: string;
  project_id: string;
  email: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email) && email.length <= 254;
}

/** 공개 페이지에서 신청 저장. RLS 정책상 '게시된 프로젝트'에만 insert 허용. */
export async function collectLead(
  supabase: SupabaseClient,
  projectId: string,
  email: string,
  meta?: Record<string, unknown>,
): Promise<void> {
  const { error } = await supabase
    .from("leads")
    .insert({ project_id: projectId, email: email.toLowerCase(), meta: meta ?? null });
  if (error) throw new Error(error.message);
}

/** 프로젝트별 신청자 목록(소유자만 RLS로 조회 가능). */
export async function selectLeads(supabase: SupabaseClient, projectId: string): Promise<LeadRow[]> {
  const { data, error } = await supabase
    .from("leads")
    .select("*")
    .eq("project_id", projectId)
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as LeadRow[];
}
