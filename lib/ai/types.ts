// lib/ai/types.ts  [기존 — promptsite-ai-core]
// 파이프라인 전역 도메인 타입. analyzePrompt → clarifyQuestions → generateCopy 가 공유한다.

export type Lang = "ko" | "en";

/** analyzePrompt 결과: 구조화된 사업정보 + 강한 카피에 부족한 정보(missing) */
export interface BizInfo {
  service_name: string;
  target_customer: string;
  main_problem: string;
  solution: string;
  cta: string;
  tone: string;
  language: Lang;
  missing: string[];
}

export interface HeroCopy {
  headline: string;
  subheadline: string;
  cta: string;
}

export interface TextSection {
  title: string;
  body: string;
}

export interface FeatureItem {
  title: string;
  description: string;
}

export interface FeaturesSection {
  title: string;
  items: FeatureItem[];
}

export interface FaqItem {
  question: string;
  answer: string;
}

export interface FinalCta {
  headline: string;
  button: string;
}

/** generateCopy 결과: 랜딩페이지 섹션별 카피 */
export interface SectionCopy {
  hero: HeroCopy;
  problem: TextSection;
  solution: TextSection;
  features: FeaturesSection;
  faq: FaqItem[];
  cta: FinalCta;
}

/** 사용 가능한 템플릿 식별자 */
export type TemplateId = "saas-launch" | "waitlist" | "agency";
