// lib/compliance/check.ts  [신규 — 컴플라이언스 P0]
// 생성 카피(SectionCopy)를 업종 규칙으로 검사한다. 순수 함수 → 미리보기(클라이언트)와
// 게시 API(서버)가 같은 결과를 낸다. 서버는 클라이언트 결과를 믿지 않고 반드시 다시 검사한다.

import type { SectionCopy } from "@/lib/ai/types";
import type { IndustryId } from "./industries";
import { RULES, type Severity } from "./rules";

export interface Finding {
  ruleId: string;
  severity: Severity;
  /** 문제 위치(예: "hero.headline", "faq.2.answer") */
  field: string;
  fieldLabel: string;
  /** 매칭된 표현 */
  match: string;
  message: string;
  basis: string;
}

/** 카피를 (위치, 사람이 읽는 라벨, 텍스트) 목록으로 펼친다. 누락 필드는 건너뛴다. */
function flatten(copy: SectionCopy): { field: string; label: string; text: string }[] {
  const out: { field: string; label: string; text: string }[] = [];
  const push = (field: string, label: string, text: unknown) => {
    if (typeof text === "string" && text.trim()) out.push({ field, label, text });
  };
  push("hero.headline", "첫 화면 제목", copy.hero?.headline);
  push("hero.subheadline", "첫 화면 설명", copy.hero?.subheadline);
  push("hero.cta", "첫 화면 버튼", copy.hero?.cta);
  push("problem.title", "고민 제목", copy.problem?.title);
  push("problem.body", "고민 본문", copy.problem?.body);
  push("solution.title", "해결 제목", copy.solution?.title);
  push("solution.body", "해결 본문", copy.solution?.body);
  push("features.title", "특징 제목", copy.features?.title);
  (copy.features?.items ?? []).forEach((it, i) => {
    push(`features.${i}.title`, `특징 ${i + 1} 제목`, it?.title);
    push(`features.${i}.description`, `특징 ${i + 1} 설명`, it?.description);
  });
  (copy.faq ?? []).forEach((f, i) => {
    push(`faq.${i}.question`, `FAQ ${i + 1} 질문`, f?.question);
    push(`faq.${i}.answer`, `FAQ ${i + 1} 답변`, f?.answer);
  });
  push("cta.headline", "마지막 제목", copy.cta?.headline);
  push("cta.button", "마지막 버튼", copy.cta?.button);
  return out;
}

/** 업종 규칙 검사. block 이 먼저 오도록 정렬해 반환한다. */
export function checkCopy(copy: SectionCopy, industry: IndustryId): Finding[] {
  const rules = RULES.filter((r) => r.industries === "all" || r.industries.includes(industry));
  const findings: Finding[] = [];
  for (const { field, label, text } of flatten(copy)) {
    for (const rule of rules) {
      const m = rule.pattern.exec(text);
      if (!m) continue;
      findings.push({
        ruleId: rule.id,
        severity: rule.severity,
        field,
        fieldLabel: label,
        match: m[0].trim(),
        message: rule.message,
        basis: rule.basis,
      });
    }
  }
  return findings.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "block" ? -1 : 1));
}

export function hasBlocking(findings: Finding[]): boolean {
  return findings.some((f) => f.severity === "block");
}

/** 다시 생성할 때 모델에 줄 피드백 문장. */
export function findingsToFeedback(findings: Finding[]): string {
  const uniq = new Map<string, Finding>();
  for (const f of findings) uniq.set(`${f.ruleId}:${f.match}`, f);
  return [...uniq.values()].map((f) => `- "${f.match}" (${f.fieldLabel}): ${f.message}`).join("\n");
}
