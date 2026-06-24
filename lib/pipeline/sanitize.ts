// lib/pipeline/sanitize.ts — 파이프라인 산출물 정화. 생성 텍스트는 절대 그대로 신뢰하지 않는다(보안 §14).
// 짧은 필드는 lib/sanitize.sanitizeText 재사용. 본문(마크다운)은 마크다운을 보존하는 별도 처리.
// 제어문자 제거는 정규식 리터럴 대신 코드포인트 순회로(불가시 문자 의존 회피).

import { sanitizeText } from "@/lib/sanitize";

// 실제 HTML 태그(글자로 시작) — "a < b" 같은 부등호는 보존.
const HTML_TAG = /<\/?[a-zA-Z][^>]*>/g;

/** C0 제어문자/DEL 제거. 탭(09)·개행(0A)·CR(0D)은 보존. */
function stripControl(input: string): string {
  let out = "";
  for (const ch of input) {
    const c = ch.codePointAt(0) ?? 0;
    const isControl = (c <= 0x1f && c !== 0x09 && c !== 0x0a && c !== 0x0d) || c === 0x7f;
    if (!isControl) out += ch;
  }
  return out;
}

/** 한 줄/짧은 필드(제목·캡션 등): HTML 태그·제어문자 제거 + 길이 제한. */
export function sanitizeLine(input: unknown, maxLen = 300): string {
  return sanitizeText(input, maxLen);
}

/** 본문(마크다운): 실제 HTML 태그만 제거, 제어문자 제거, 마크다운/줄바꿈 유지. */
export function sanitizeBody(input: unknown, maxLen = 8000): string {
  if (typeof input !== "string") return "";
  let s = stripControl(input.replace(HTML_TAG, "")).trim();
  if (s.length > maxLen) s = s.slice(0, maxLen).trimEnd();
  return s;
}

/** 태그 1개 정화: 선행 #, 공백, 제어문자/꺾쇠 제거 + 길이 제한. */
export function sanitizeTag(input: unknown): string {
  if (typeof input !== "string") return "";
  const s = stripControl(input).replace(/[<>]/g, "").trim().replace(/^#+/, "").trim();
  return s.slice(0, 30);
}

/** 문자열 배열 정화 + 빈 항목 제거 + 최대 개수 제한. */
export function strList(v: unknown, maxItems: number, maxLen = 300): string[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((x) => sanitizeLine(x, maxLen))
    .filter(Boolean)
    .slice(0, maxItems);
}

/** 대소문자/공백 무시 중복 제거(순서 보존). */
export function dedupeTags(tags: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of tags) {
    const key = t.toLowerCase().replace(/\s+/g, "");
    if (key && !seen.has(key)) {
      seen.add(key);
      out.push(t);
    }
  }
  return out;
}
