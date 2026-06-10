// lib/ai/renderPage.tsx
// 템플릿 식별자 + copy(+테마·브랜드·신청 폼 슬롯) → 렌더된 엘리먼트.
// 컴포넌트는 정적 import 후 switch 로 선택(동적 컴포넌트 생성 금지 규칙 준수).
// 주의: 서버 전용(core/SDK)은 import 하지 않는다 → 클라이언트 번들 안전.

import type { ReactNode } from "react";
import type { Lang, SectionCopy, TemplateId } from "./types";
import { THEMES, type Theme } from "./theme";
import SaasLaunch from "@/components/templates/SaasLaunch";
import Waitlist from "@/components/templates/Waitlist";
import Agency from "@/components/templates/Agency";

export interface TemplateMeta {
  id: TemplateId;
  name: string;
  description: string;
}

export const TEMPLATE_META: TemplateMeta[] = [
  { id: "saas-launch", name: "SaaS Launch", description: "제품·서비스 출시. 기능 강조형." },
  { id: "waitlist", name: "Waitlist", description: "사전 등록·대기자 모집. 미니멀 다크." },
  { id: "agency", name: "Agency", description: "대행·컨설팅·전문 서비스. 신뢰 중심." },
];

export interface RenderOptions {
  lang?: Lang;
  theme?: Theme;
  brand?: string;
  signupSlot?: ReactNode;
}

/** 템플릿 식별자 + copy 를 받아 해당 템플릿 엘리먼트를 반환. 알 수 없는 id는 기본 템플릿. */
export function renderTemplate(templateId: TemplateId, copy: SectionCopy, opts: RenderOptions = {}) {
  const { lang = "ko", theme = THEMES.indigo, brand = "", signupSlot } = opts;
  switch (templateId) {
    case "waitlist":
      return <Waitlist copy={copy} lang={lang} theme={theme} brand={brand} signupSlot={signupSlot} />;
    case "agency":
      return <Agency copy={copy} lang={lang} theme={theme} brand={brand} signupSlot={signupSlot} />;
    case "saas-launch":
    default:
      return <SaasLaunch copy={copy} lang={lang} theme={theme} brand={brand} signupSlot={signupSlot} />;
  }
}
