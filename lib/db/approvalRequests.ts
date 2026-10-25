// lib/db/approvalRequests.ts  [신규 — P2 대행사 모드] — 사장님 승인 요청 링크(서버 전용).
// 요청 생성·목록은 로그인 세션(RLS 소유자), 링크 열람·승인은 로그인 없는 사장님이 하므로 관리자(service_role) 클라이언트로 처리한다.

import { randomBytes } from "node:crypto";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { SectionCopy, TemplateId } from "@/lib/ai/types";
import type { Disclosures, IndustryId } from "@/lib/compliance/industries";
import type { PlaceInfo, Translations } from "@/lib/i18n/langs";
import { hashToken } from "./apiTokens";

/** 요청 시점의 게시 설정 스냅샷. */
export interface ApprovalDraft {
  industry: IndustryId;
  ai_label: boolean;
  label_off_ack: boolean;
  disclosures: Disclosures;
  /** 매장 정보·번역본도 승인 대상 내용이다 */
  place?: PlaceInfo;
  translations?: Translations;
}

export interface ApprovalRequestRow {
  id: string;
  project_id: string;
  owner: string;
  template: TemplateId;
  copy: SectionCopy;
  draft: ApprovalDraft;
  status: "pending" | "approved" | "cancelled";
  created_at: string;
  expires_at: string;
  approved_at: string | null;
  approver_name: string | null;
}

export const APPROVAL_TTL_DAYS = 7;

export async function createApprovalRequest(
  supabase: SupabaseClient,
  owner: string,
  input: { projectId: string; template: TemplateId; copy: SectionCopy; draft: ApprovalDraft },
): Promise<{ token: string; expiresAt: string }> {
  // 같은 페이지의 이전 대기 요청은 취소한다(가장 최근 내용만 승인 가능)
  await supabase
    .from("approval_requests")
    .update({ status: "cancelled" })
    .eq("project_id", input.projectId)
    .eq("owner", owner)
    .eq("status", "pending");

  const token = "ap_" + randomBytes(24).toString("base64url");
  const expiresAt = new Date(Date.now() + APPROVAL_TTL_DAYS * 86_400_000).toISOString();
  const { error } = await supabase.from("approval_requests").insert({
    project_id: input.projectId,
    owner,
    token_hash: hashToken(token),
    template: input.template,
    copy: input.copy,
    draft: input.draft,
    expires_at: expiresAt,
  });
  if (error) throw new Error(error.message);
  return { token, expiresAt };
}

/** 내 대기 중 요청의 프로젝트 id 목록(대시보드 배지용). */
export async function selectPendingProjectIds(supabase: SupabaseClient, owner: string): Promise<Set<string>> {
  const { data, error } = await supabase
    .from("approval_requests")
    .select("project_id, expires_at")
    .eq("owner", owner)
    .eq("status", "pending");
  if (error) throw new Error(error.message);
  const now = Date.now();
  return new Set((data ?? []).filter((r) => Date.parse(r.expires_at) > now).map((r) => r.project_id as string));
}

/** 링크 토큰으로 요청 조회(관리자 클라이언트). */
export async function selectRequestByToken(admin: SupabaseClient, token: string): Promise<ApprovalRequestRow | null> {
  if (!token.startsWith("ap_")) return null;
  const { data, error } = await admin.from("approval_requests").select("*").eq("token_hash", hashToken(token)).maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ApprovalRequestRow) ?? null;
}

/** 대기 중인 요청만 승인 완료로 바꾼다(동시 승인 방지). 바뀌었으면 true. */
export async function markRequestApproved(admin: SupabaseClient, id: string, approverName: string): Promise<boolean> {
  const { data, error } = await admin
    .from("approval_requests")
    .update({ status: "approved", approved_at: new Date().toISOString(), approver_name: approverName })
    .eq("id", id)
    .eq("status", "pending")
    .select("id");
  if (error) throw new Error(error.message);
  return (data ?? []).length > 0;
}

export function isExpired(row: Pick<ApprovalRequestRow, "expires_at">): boolean {
  return Date.parse(row.expires_at) <= Date.now();
}
