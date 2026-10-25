// lib/compliance/feed.ts  [신규 — 컴플라이언스 P1 규제 피드]
// 업종 프리셋·금칙어 규칙·AI 고지 문구를 직렬화 가능한 JSON 으로 묶는다.
// 블로그·카페·쇼츠·스레드 등 다른 곰대리 프로그램이 같은 규칙을 원격으로 받아 쓰게 하는 단일 출처.
// 정규식은 source + flags 문자열로 내보낸다(JS RegExp, Python re, Rust regex 에서 그대로 쓸 수 있는 문법만 사용).

import { DISCLOSURE_META, INDUSTRIES } from "./industries";
import { RULES, RULES_VERSION } from "./rules";
import { AI_NOTICE_VERSION, AI_PRE_NOTICE, aiOutputLabel } from "./notice";
import { FOREIGN_LANGS } from "@/lib/i18n/langs";

export interface RulesFeed {
  version: string;
  notice_version: string;
  disclaimer: string;
  industries: { id: string; name: string; prompt_rules: string[]; required: string[] }[];
  disclosures: Record<string, { label: string; placeholder: string; max_len: number }>;
  rules: {
    id: string;
    industries: string[] | "all";
    severity: "block" | "warn";
    pattern: string;
    flags: string;
    message: string;
    basis: string;
  }[];
  notices: { pre_notice: string; ai_label: Record<string, string> };
}

export function buildRulesFeed(): RulesFeed {
  return {
    version: RULES_VERSION,
    notice_version: AI_NOTICE_VERSION,
    disclaimer: "2026-10 기준 조사 결과를 바탕으로 한 자동 검사 규칙이며 법률 자문이 아닙니다.",
    industries: INDUSTRIES.map((i) => ({ id: i.id, name: i.name, prompt_rules: i.promptRules, required: i.required })),
    disclosures: Object.fromEntries(
      Object.entries(DISCLOSURE_META).map(([k, v]) => [k, { label: v.label, placeholder: v.placeholder, max_len: v.maxLen }]),
    ),
    rules: RULES.map((r) => ({
      id: r.id,
      industries: r.industries,
      severity: r.severity,
      pattern: r.pattern.source,
      flags: r.pattern.flags,
      message: r.message,
      basis: r.basis,
    })),
    notices: {
      pre_notice: AI_PRE_NOTICE,
      ai_label: Object.fromEntries((["ko", ...FOREIGN_LANGS] as const).map((l) => [l, aiOutputLabel(l)])),
    },
  };
}
