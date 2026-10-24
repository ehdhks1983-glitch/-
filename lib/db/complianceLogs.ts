// lib/db/complianceLogs.ts  [신규 — 컴플라이언스 P1] — 게시 승인 감사 로그(append-only).
// 승인 기록과 그때의 카피·템플릿 스냅샷을 남긴다. 로그 실패가 게시를 막지는 않는다(호출부에서 처리).

import type { SupabaseClient } from "@supabase/supabase-js";
import type { SectionCopy, TemplateId } from "@/lib/ai/types";
import type { ComplianceRecord } from "@/lib/compliance/approval";

export async function insertComplianceLog(
  supabase: SupabaseClient,
  entry: { projectId: string; owner: string; record: ComplianceRecord; template: TemplateId; copy: SectionCopy },
): Promise<void> {
  const { error } = await supabase.from("compliance_logs").insert({
    project_id: entry.projectId,
    owner: entry.owner,
    record: entry.record,
    template: entry.template,
    copy: entry.copy,
  });
  if (error) throw new Error(error.message);
}

/** 감사 로그 기록. 실패는 서버 로그로만 남기고 게시 흐름은 계속한다(스키마 미적용 DB 호환). */
export async function logApproval(
  supabase: SupabaseClient,
  entry: Parameters<typeof insertComplianceLog>[1],
): Promise<void> {
  try {
    await insertComplianceLog(supabase, entry);
  } catch (err) {
    console.error("[compliance_logs] 기록 실패:", err);
  }
}
