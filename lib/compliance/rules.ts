// lib/compliance/rules.ts  [신규 — 컴플라이언스 P0]
// 업종별 금칙어 규칙. block = 게시 불가(다시 생성 필요), warn = 승인 시 확인 후 게시 가능.
// 정규식은 "효능·보장을 단정하는 문형" 위주로 좁게 잡아 오탐을 줄인다(단어 하나만으로 막지 않음).
// 근거(basis)는 2026-10 기준 조사 보고서(reports/곰대리 자동화 2026 기능 업데이트.md) 요약이며 법률 자문이 아니다.

import type { IndustryId } from "./industries";

/** 규칙·업종 프리셋을 바꾸면 올린다. 규제 피드(/api/compliance/rules)를 받는 다른 프로그램이 이 값으로 갱신을 판단한다. */
export const RULES_VERSION = "2026-10-25";

export type Severity = "block" | "warn";

export interface ComplianceRule {
  id: string;
  industries: IndustryId[] | "all";
  severity: Severity;
  pattern: RegExp;
  message: string;
  basis: string;
}

const EXPERT_ENDORSE = /(의사|약사|한의사|전문의|의학박사|교수)\s*(가|이|님이|님께서)?\s*(직접\s*)?(강력\s*)?(추천|인정|보증)/;
const CUSTOMER_TESTIMONIAL =
  /((먹어|써|발라|사용해|받아|다녀|들어)\s*(봤|보았|보니)(는데|어요|습니다|더니)?|(고객|손님|회원|수강생|환자)(님|분)?들?\s*(이|의|께서)?\s*(극찬|칭찬|후기|리뷰|만족)|후기가\s*(증명|말해))/;

export const RULES: ComplianceRule[] = [
  // ───────────── 전 업종 공통 ─────────────
  {
    id: "superlative",
    industries: ["general", "food", "beauty", "academy", "health_food", "cosmetics"],
    severity: "warn",
    pattern: /(최고|최초|유일|1위|일등|넘버원|no\.?\s?1)/i,
    message: "최상급·순위 표현은 객관적 근거(실증 자료)가 있어야 합니다. 근거가 없으면 빼 주세요.",
    basis: "표시광고법·실증고시(2026-09-03 개정 시행)",
  },
  {
    id: "guarantee",
    industries: "all",
    severity: "warn",
    pattern: /(100\s?%|백\s?퍼센트|무조건|보장)/,
    message: "효과·결과를 보장하는 표현은 실증이 필요합니다. 사실과 다르면 부당광고가 될 수 있어요.",
    basis: "표시광고법·실증고시",
  },
  {
    id: "ai_performance",
    industries: "all",
    severity: "warn",
    pattern: /AI\s*(기술|기반)?\s*(로|으로)\s*(더\s*)?(안전|정확|효과|똑똑)/i,
    message: "'AI 기술로 더 ~한' 같은 성능 표현은 사전 실증이 필요합니다.",
    basis: "실증고시(2026-09-03 개정 시행)",
  },
  {
    id: "expert_endorsement",
    industries: ["general", "beauty", "academy"],
    severity: "warn",
    pattern: EXPERT_ENDORSE,
    message: "전문가가 추천·보증하는 형식입니다. 실제 인물·사실이 아니면 빼 주세요.",
    basis: "추천·보증 심사지침(2026-06-01 개정 시행)",
  },
  {
    id: "expert_endorsement_regulated",
    industries: ["food", "health_food", "cosmetics", "medical"],
    severity: "block",
    pattern: EXPERT_ENDORSE,
    message: "의사·약사 등 전문가가 추천하는 형식은 쓸 수 없습니다. AI 가상 전문가의 식품·의약품 추천은 2026-11-27부터 형사처벌 대상입니다.",
    basis: "식품표시광고법·약사법 개정(2026-11-27 시행), 의료법 제56조",
  },
  {
    id: "testimonial",
    industries: ["general", "food", "beauty", "academy", "cosmetics"],
    severity: "warn",
    pattern: CUSTOMER_TESTIMONIAL,
    message: "손님 후기·체험담처럼 보이는 문장입니다. 실제 후기가 아니면 빼고, 실제 후기라도 원문과 동의를 확인하세요.",
    basis: "추천·보증 심사지침 — 경험하지 않은 체험담은 부당광고",
  },
  {
    id: "testimonial_regulated",
    industries: ["medical", "health_food"],
    severity: "block",
    pattern: CUSTOMER_TESTIMONIAL,
    message: "이 업종은 치료경험담·소비자 체험기를 광고에 쓸 수 없습니다.",
    basis: "의료법 제56조, 건강기능식품 표시·광고 기준",
  },

  // ───────────── 식품·건강기능식품 ─────────────
  {
    id: "food_disease",
    industries: ["food", "health_food"],
    severity: "block",
    pattern:
      /(항암|암\s?(예방|치료|억제)|당뇨|고혈압|혈압\s?(조절|강하|을\s?낮)|혈당\s?(조절|강하|개선|을\s?낮)|콜레스테롤\s?(감소|개선|을\s?낮)|면역력\s?(강화|증진|향상|을\s?높)|질병\s?(예방|치료)|(병|질환)\s?(을|를)?\s?(예방|치료|낫)|치료\s?효과|노화\s?(방지|예방|억제))/,
    message: "질병 예방·치료나 노화 방지 효능을 표방하는 표현은 쓸 수 없습니다.",
    basis: "식품표시광고법 제8조",
  },
  {
    id: "food_diet",
    industries: ["food"],
    severity: "warn",
    pattern: /(살이\s?빠|체지방\s?(감소|분해|을\s?줄)|다이어트\s?효과|붓기\s?(제거|가\s?빠))/,
    message: "체중 감량 효능은 일반 식품을 건강기능식품처럼 보이게 할 수 있어요.",
    basis: "식품표시광고법 제8조(건강기능식품 오인)",
  },

  // ───────────── 화장품 ─────────────
  {
    id: "cosmetics_medical",
    industries: ["cosmetics"],
    severity: "block",
    pattern:
      /((아토피|여드름|습진|건선|피부염|탈모|무좀)\s?(을|를)?\s?(치료|완치|낫)|(피부|세포)\s?재생|염증\s?(을|를)?\s?(치료|완화|제거)|발모)/,
    message: "의약품으로 오인될 수 있는 치료·재생 표현은 화장품 광고에 쓸 수 없습니다.",
    basis: "화장품법(의약품 오인 광고 금지)",
  },
  {
    id: "cosmetics_functional",
    industries: ["cosmetics"],
    severity: "warn",
    pattern: /(주름\s?(개선|제거|완화)|미백|자외선\s?차단)/,
    message: "기능성화장품 심사·보고를 받은 제품만 쓸 수 있는 표현입니다.",
    basis: "화장품법(기능성화장품 표시)",
  },

  // ───────────── 의료 ─────────────
  {
    id: "medical_safety",
    industries: ["medical"],
    severity: "block",
    pattern: /(부작용\s?(이|은)?\s?없|통증\s?(이|은)?\s?없|무통|완치|재발\s?(이|은)?\s?없|100\s?%\s?(안전|성공))/,
    message: "부작용·통증이 없다거나 완치를 약속하는 의료 광고는 금지됩니다.",
    basis: "의료법 제56조",
  },
  {
    id: "medical_superlative",
    industries: ["medical"],
    severity: "block",
    pattern: /(최고|최초|유일|1위|최상|넘버원|no\.?\s?1)/i,
    message: "의료 광고에는 비교·과장 표현을 쓸 수 없습니다.",
    basis: "의료법 제56조",
  },
  {
    id: "medical_before_after",
    industries: ["medical"],
    severity: "block",
    pattern: /(전후\s?(사진|비교)|비포\s?애프터|before\s?&?\s?after)/i,
    message: "시술 전후 비교 광고는 금지됩니다.",
    basis: "의료법 제56조",
  },
  {
    id: "medical_inducement",
    industries: ["medical"],
    severity: "warn",
    pattern: /(무료\s?(시술|진료|검진|상담\s?이벤트)|할인\s?이벤트|이벤트\s?가)/,
    message: "할인·무료 시술 문구는 환자 유인으로 문제될 수 있어요.",
    basis: "의료법 제27조·제56조",
  },

  // ───────────── 학원 ─────────────
  {
    id: "academy_guarantee",
    industries: ["academy"],
    severity: "block",
    pattern: /(합격\s?(을\s?)?보장|100\s?%\s?합격|합격률\s?\d|성적\s?(향상\s?)?(을\s?)?보장|등급\s?(상승\s?)?보장)/,
    message: "합격·성적을 보장하거나 근거 없는 합격률을 쓰면 과장 광고가 됩니다.",
    basis: "학원법·표시광고법",
  },

  // ───────────── 미용 ─────────────
  {
    id: "beauty_medical",
    industries: ["beauty"],
    severity: "block",
    pattern: /(탈모\s?(치료|완치)|두피\s?치료|모발\s?재생|발모|필러|보톡스|레이저\s?(시술|제모|토닝)|치료\s?효과)/,
    message: "미용업소가 의료 효과나 의료행위를 광고할 수 없습니다.",
    basis: "의료법(무면허 의료행위)·공중위생관리법",
  },
];
