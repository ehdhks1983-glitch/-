// lib/i18n/translations.ts  [신규 — P2 외국인 손님 패키지]
// 번역본 입력 정리(저장·게시 전). 알 수 없는 언어는 버리고, 문구는 렌더와 같은 규칙으로 정화한다.

import { sanitizeCopy, sanitizeText } from "@/lib/sanitize";
import { FOREIGN_LANGS, type Translation, type Translations } from "./langs";

const MAX_HASHTAGS = 10;
/** 구글 비즈니스 프로필 소개 글자 수 한도(750자) */
export const SUMMARY_MAX = 750;

export function parseTranslation(input: unknown): Translation | null {
  if (!input || typeof input !== "object") return null;
  const r = input as Record<string, unknown>;
  const copy = sanitizeCopy(r.copy as never);
  if (!copy.hero.headline) return null;
  const hashtags = Array.isArray(r.hashtags)
    ? r.hashtags
        .map((h) => sanitizeText(h, 40).replace(/\s+/g, ""))
        .filter(Boolean)
        .map((h) => (h.startsWith("#") ? h : `#${h}`))
        .slice(0, MAX_HASHTAGS)
    : [];
  return { copy, summary: sanitizeText(r.summary, SUMMARY_MAX), hashtags, hours: sanitizeText(r.hours, 120) };
}

export function parseTranslations(input: unknown): Translations {
  if (!input || typeof input !== "object") return {};
  const r = input as Record<string, unknown>;
  const out: Translations = {};
  for (const lang of FOREIGN_LANGS) {
    const t = parseTranslation(r[lang]);
    if (t) out[lang] = t;
  }
  return out;
}
