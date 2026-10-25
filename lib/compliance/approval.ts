// lib/compliance/approval.ts  [신규 — 컴플라이언스 P0]
// 게시 전 사장님 승인. 클라이언트가 보낸 승인 입력을 검증하고, 서버가 카피를 다시 검사해
// 통과할 때만 승인 기록(ComplianceRecord)을 만든다. 기록은 projects.compliance(jsonb)에 저장된다.

import type { SectionCopy } from "@/lib/ai/types";
import { sanitizeCopy, sanitizeText } from "@/lib/sanitize";
import {
  DISCLOSURE_META,
  getIndustry,
  isIndustryId,
  missingDisclosures,
  type DisclosureField,
  type Disclosures,
  type IndustryId,
} from "./industries";
import { checkCopy, hasBlocking, type Finding } from "./check";
import { AI_NOTICE_VERSION } from "./notice";

/** 클라이언트 → 서버 승인 입력. */
export interface ApprovalInput {
  industry: IndustryId;
  /** 공개 페이지에 AI 생성 표시를 보일지(기본 true) */
  ai_label: boolean;
  /** ai_label=false 일 때 "직접 검토·편집했고 책임을 이해함" 확인 */
  label_off_ack: boolean;
  disclosures: Disclosures;
  /** "내용을 직접 확인했다" 승인 체크 */
  approved: boolean;
}

/** DB(projects.compliance)에 남는 승인 기록. */
export interface ComplianceRecord {
  industry: IndustryId;
  ai_label: boolean;
  label_off_ack: boolean;
  disclosures: Disclosures;
  approved_at: string;
  approved_by: string;
  notice_version: string;
  /** 승인 당시 남아 있던 경고(warn) 규칙 — 감사용 */
  warnings: string[];
  /** 승인 경로: 계정 주인이 직접(owner) / 대행사가 보낸 링크로 사장님이(client_link) */
  approved_via?: "owner" | "client_link";
  /** client_link 승인 시 사장님이 적은 이름 */
  approver_name?: string;
}

export function parseApproval(input: unknown): ApprovalInput | null {
  if (!input || typeof input !== "object") return null;
  const r = input as Record<string, unknown>;
  if (!isIndustryId(r.industry)) return null;
  const rawDisc = r.disclosures && typeof r.disclosures === "object" ? (r.disclosures as Record<string, unknown>) : {};
  const disclosures: Disclosures = {};
  for (const field of getIndustry(r.industry).required) {
    const v = sanitizeText(rawDisc[field], DISCLOSURE_META[field].maxLen);
    if (v) disclosures[field] = v;
  }
  return {
    industry: r.industry,
    ai_label: r.ai_label !== false,
    label_off_ack: r.label_off_ack === true,
    disclosures,
    approved: r.approved === true,
  };
}

export type ApprovalResult =
  | { ok: true; record: Omit<ComplianceRecord, "approved_by"> }
  | { ok: false; error: string; findings?: Finding[]; missing?: DisclosureField[] };

/** 게시할 카피와 승인 입력을 검증한다. 서버에서 호출(클라이언트 검사 결과는 신뢰하지 않음). */
export function validateApproval(copy: SectionCopy, approval: ApprovalInput | null): ApprovalResult {
  if (!approval) return { ok: false, error: "업종 선택과 게시 전 확인이 필요해요." };
  if (!approval.approved) return { ok: false, error: "게시 전에 내용을 확인하고 승인해 주세요." };
  if (!approval.ai_label && !approval.label_off_ack) {
    return { ok: false, error: "AI 표시를 끄려면 직접 검토·수정했다는 확인이 필요해요." };
  }
  const missing = missingDisclosures(approval.industry, approval.disclosures);
  if (missing.length) {
    return {
      ok: false,
      error: `필수 표시 항목을 입력해 주세요: ${missing.map((f) => DISCLOSURE_META[f].label).join(", ")}`,
      missing,
    };
  }
  const findings = checkCopy(sanitizeCopy(copy), approval.industry);
  if (hasBlocking(findings)) {
    return {
      ok: false,
      error: "광고 규정상 쓸 수 없는 표현이 있어 게시할 수 없어요. '다시 생성'으로 고친 뒤 게시해 주세요.",
      findings,
    };
  }
  return {
    ok: true,
    record: {
      industry: approval.industry,
      ai_label: approval.ai_label,
      label_off_ack: approval.ai_label ? false : approval.label_off_ack,
      disclosures: approval.disclosures,
      approved_at: new Date().toISOString(),
      notice_version: AI_NOTICE_VERSION,
      warnings: [...new Set(findings.map((f) => f.ruleId))],
    },
  };
}
