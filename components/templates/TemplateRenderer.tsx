// components/templates/TemplateRenderer.tsx
// 단일 렌더 진입점: copy 를 sanitize 하고, biz 로 테마·브랜드를 도출해 템플릿에 주입.
// 미리보기/공개 페이지가 공통으로 사용. 훅 없음 → 서버/클라이언트 양쪽에서 렌더 가능.

import type { ReactNode } from "react";
import type { BizInfo, Lang, SectionCopy, TemplateId } from "@/lib/ai/types";
import { renderTemplate } from "@/lib/ai/renderPage";
import { selectTheme } from "@/lib/ai/theme";
import { sanitizeCopy, sanitizeText } from "@/lib/sanitize";

export default function TemplateRenderer({
  templateId,
  copy,
  lang = "ko",
  biz,
  signupSlot,
}: {
  templateId: TemplateId;
  copy: SectionCopy;
  lang?: Lang;
  /** 테마(업종 팔레트)·브랜드명 도출용. 없으면 기본 테마. */
  biz?: BizInfo | null;
  /** 공개 페이지 신청 폼 등 푸터 직전에 끼울 섹션. */
  signupSlot?: ReactNode;
}) {
  return renderTemplate(templateId, sanitizeCopy(copy), {
    lang,
    theme: selectTheme(biz),
    brand: sanitizeText(biz?.service_name, 60),
    signupSlot,
  });
}
