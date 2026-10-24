// components/ComplianceFooter.tsx  [신규 — 컴플라이언스 P0]
// 공개 페이지 하단 고지 띠: AI 생성 표시(AI 기본법 결과물 표시) + 업종별 필수 표시 항목
// (학원 등록번호·교습비, 건기식 자율심의 번호). 미리보기에도 같은 모양으로 보여 준다.
// 훅 없음 → 서버/클라이언트 양쪽에서 렌더 가능.

import type { Lang } from "@/lib/ai/types";
import { DISCLOSURE_META, getIndustry, type Disclosures, type IndustryId } from "@/lib/compliance/industries";
import { aiOutputLabel } from "@/lib/compliance/notice";
import { sanitizeText } from "@/lib/sanitize";

export default function ComplianceFooter({
  lang = "ko",
  aiLabel = true,
  industry = "general",
  disclosures,
}: {
  lang?: Lang;
  aiLabel?: boolean;
  industry?: IndustryId;
  disclosures?: Disclosures;
}) {
  const items = getIndustry(industry)
    .required.map((f) => ({ label: DISCLOSURE_META[f].label, value: sanitizeText(disclosures?.[f], DISCLOSURE_META[f].maxLen) }))
    .filter((i) => i.value);

  if (!aiLabel && items.length === 0) return null;

  return (
    <div className="border-t border-slate-200 bg-slate-50 px-6 py-4 text-center text-xs leading-6 text-slate-500">
      {items.length > 0 && (
        <p>
          {items.map((i, idx) => (
            <span key={i.label}>
              {idx > 0 && " · "}
              {i.label}: {i.value}
            </span>
          ))}
        </p>
      )}
      {aiLabel && <p>{aiOutputLabel(lang)}</p>}
    </div>
  );
}
