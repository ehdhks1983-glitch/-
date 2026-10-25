// lib/ai/translateCopy.ts  [신규 — P2 외국인 손님 패키지]
// 원문 카피(한국어) → 외국인 손님용 번역본(페이지 문구 + 구글 비즈니스 프로필 소개문·해시태그 + 영업시간).
// 원칙: 뜻만 옮기고 새 주장·수치·효능·후기를 더하지 않는다(게시 승인은 원문 검사 결과 기준이기 때문).

import { withFallback, safeParseJson } from "./core";
import type { SectionCopy } from "./types";
import type { ForeignLang, Translation } from "@/lib/i18n/langs";
import { parseTranslation, SUMMARY_MAX } from "@/lib/i18n/translations";

const LANG_PROMPT: Record<ForeignLang, string> = {
  en: "English (natural, friendly tone for international visitors)",
  ja: "Japanese (丁寧語, natural for Japanese tourists)",
  "zh-CN": "Simplified Chinese (for mainland Chinese visitors)",
  "zh-TW": "Traditional Chinese (Taiwan/Hong Kong visitors; use Taiwan usage)",
};

function buildSystem(lang: ForeignLang): string {
  return `You translate Korean small-business landing page copy for foreign tourists into ${LANG_PROMPT[lang]}.
Output ONLY one JSON object — no prose, no markdown, no code fences.
[Rules]
- Translate the meaning faithfully. Never add claims, numbers, health effects, reviews, rankings or guarantees that are not in the source.
- Keep brand/menu proper nouns in their original romanization; add a short meaning in parentheses if helpful.
- Keep it natural and short; same structure and item counts as the source.
- summary: a factual business description for a Google Business Profile in the target language (max ${SUMMARY_MAX} characters, no superlatives, no prices unless in source).
- hashtags: 5-8 hashtags in the target language useful for tourists (include the city/area if it appears in the source), each starting with #.
- hours: translate the given opening hours text; empty string if none given.
Schema:
{ "copy": { "hero":{"headline":"","subheadline":"","cta":""}, "problem":{"title":"","body":""},
  "solution":{"title":"","body":""}, "features":{"title":"","items":[{"title":"","description":""}]},
  "faq":[{"question":"","answer":""}], "cta":{"headline":"","button":""} },
  "summary":"", "hashtags":[""], "hours":"" }`;
}

export async function translateCopy(
  copy: SectionCopy,
  lang: ForeignLang,
  ctx: { serviceName: string; hours?: string },
): Promise<Translation> {
  const raw = await withFallback("translate", {
    system: buildSystem(lang),
    user: JSON.stringify({ service_name: ctx.serviceName, hours: ctx.hours ?? "", copy }, null, 2),
    json: true,
  });
  const parsed = safeParseJson<Record<string, unknown>>(raw);
  // 일부 모델이 copy 래퍼 없이 카피만 돌려주는 경우도 받아 준다
  const t = parseTranslation("copy" in parsed ? parsed : { copy: parsed });
  if (!t) throw new Error(`번역 결과가 비어 있음(${lang})`);
  return t;
}
