// components/templates/TemplateRenderer.tsx  [신규]
// 단일 렌더 진입점: copy를 sanitize 후 renderPage 로 주입한다.
// 미리보기/공개 페이지가 공통으로 사용. 훅 없음 → 서버/클라이언트 양쪽에서 렌더 가능.

import type { Lang, SectionCopy, TemplateId } from "@/lib/ai/types";
import { renderTemplate } from "@/lib/ai/renderPage";
import { sanitizeCopy } from "@/lib/sanitize";

export default function TemplateRenderer({
  templateId,
  copy,
  lang = "ko",
}: {
  templateId: TemplateId;
  copy: SectionCopy;
  lang?: Lang;
}) {
  return renderTemplate(templateId, sanitizeCopy(copy), lang);
}
