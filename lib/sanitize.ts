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

/** SectionCopy 전체 정화 — 렌더 직전에 한 번 호출(미리보기/공개 페이지 공통). */
export function sanitizeCopy(c: SectionCopy): SectionCopy {
  return {
    hero: {
      headline: sanitizeText(c.hero.headline, 200),
      subheadline: sanitizeText(c.hero.subheadline, 400),
      cta: sanitizeText(c.hero.cta, 60),
    },
    problem: {
      title: sanitizeText(c.problem.title, 200),
      body: sanitizeText(c.problem.body, 1200),
    },
    solution: {
      title: sanitizeText(c.solution.title, 200),
      body: sanitizeText(c.solution.body, 1200),
    },
    features: {
      title: sanitizeText(c.features.title, 200),
      items: c.features.items.map((i) => ({
        title: sanitizeText(i.title, 120),
        description: sanitizeText(i.description, 400),
      })),
    },
    faq: c.faq.map((f) => ({
      question: sanitizeText(f.question, 200),
      answer: sanitizeText(f.answer, 800),
    })),
    cta: {
      headline: sanitizeText(c.cta.headline, 200),
      button: sanitizeText(c.cta.button, 60),
    },
  };
}
