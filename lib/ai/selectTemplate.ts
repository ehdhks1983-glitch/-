// lib/ai/selectTemplate.ts  [신규]
// 구조화된 사업정보(BizInfo) → 가장 어울리는 템플릿 추천.
// 별도 모델 호출 없이 키워드 휴리스틱으로 결정(빠르고 결정적, 비용 0).

import type { BizInfo, TemplateId } from "./types";

const WAITLIST_KEYWORDS = [
  "대기", "사전", "출시 예정", "출시예정", "사전예약", "사전 예약", "베타",
  "waitlist", "wait list", "coming soon", "beta", "early access", "pre-launch", "prelaunch",
];

const AGENCY_KEYWORDS = [
  "대행", "컨설팅", "에이전시", "외주", "스튜디오", "용역", "마케팅 대행",
  "agency", "consult", "studio", "freelance", "services", "done-for-you",
];

/** 사업정보 텍스트를 합쳐 키워드로 템플릿을 추천한다. 기본값은 saas-launch. */
export function selectTemplate(biz: BizInfo): TemplateId {
  const haystack = [
    biz.service_name,
    biz.target_customer,
    biz.main_problem,
    biz.solution,
    biz.cta,
    biz.tone,
  ]
    .join(" ")
    .toLowerCase();

  const has = (keywords: string[]) => keywords.some((k) => haystack.includes(k));

  if (has(WAITLIST_KEYWORDS)) return "waitlist";
  if (has(AGENCY_KEYWORDS)) return "agency";
  return "saas-launch";
}
