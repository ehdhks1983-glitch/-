// lib/sanitize.ts  [신규]
// AI 생성 텍스트 정화. React는 문자열 children을 기본 이스케이프하므로(=XSS 안전),
// 여기서는 추가 방어로 HTML 태그·제어문자 제거 + 길이 제한을 한 번 더 적용한다.
// 규칙: 생성 텍스트를 절대 dangerouslySetInnerHTML 에 넣지 않는다(핸드오프 보안).

import type { SectionCopy } from "./ai/types";

/** C0 제어문자/DEL 제거(탭 0x09·개행 0x0A·CR 0x0D 은 보존). 코드포인트로 판별. */
function stripControlChars(input: string): string {
  let out = "";
  for (const ch of input) {
    const code = ch.codePointAt(0) ?? 0;
    const isControl = (code <= 0x1f && code !== 0x09 && code !== 0x0a && code !== 0x0d) || code === 0x7f;
    if (!isControl) out += ch;
  }
  return out;
}

/** 단일 문자열 정화: 태그/제어문자 제거 + 트림 + 길이 제한. */
export function sanitizeText(input: unknown, maxLen = 2000): string {
  if (typeof input !== "string") return "";
  let s = stripControlChars(input.replace(/<[^>]*>/g, "")).trim();
  if (s.length > maxLen) s = s.slice(0, maxLen).trimEnd();
  return s;
}

/** SectionCopy 전체 정화 — 렌더 직전에 한 번 호출(미리보기/공개 페이지 공통).
 *  DB의 copy 가 비어있거나 일부만 있어도 크래시하지 않도록 누락 필드를 안전 처리한다. */
export function sanitizeCopy(c: Partial<SectionCopy> | null | undefined): SectionCopy {
  const safe = c ?? {};
  return {
    hero: {
      headline: sanitizeText(safe.hero?.headline, 200),
      subheadline: sanitizeText(safe.hero?.subheadline, 400),
      cta: sanitizeText(safe.hero?.cta, 60),
    },
    problem: {
      title: sanitizeText(safe.problem?.title, 200),
      body: sanitizeText(safe.problem?.body, 1200),
    },
    solution: {
      title: sanitizeText(safe.solution?.title, 200),
      body: sanitizeText(safe.solution?.body, 1200),
    },
    features: {
      title: sanitizeText(safe.features?.title, 200),
      items: Array.isArray(safe.features?.items)
        ? safe.features.items.map((i) => ({
            title: sanitizeText(i?.title, 120),
            description: sanitizeText(i?.description, 400),
          }))
        : [],
    },
    faq: Array.isArray(safe.faq)
      ? safe.faq.map((f) => ({
          question: sanitizeText(f?.question, 200),
          answer: sanitizeText(f?.answer, 800),
        }))
      : [],
    cta: {
      headline: sanitizeText(safe.cta?.headline, 200),
      button: sanitizeText(safe.cta?.button, 60),
    },
  };
}
