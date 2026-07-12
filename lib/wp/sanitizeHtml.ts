// lib/wp/sanitizeHtml.ts  [신규 — 워드프레스 자동 발행]
// AI가 만든 본문 HTML 정화. 허용 태그만 "재조립"해서 내보낸다:
// 통과한 태그도 원문을 그대로 쓰지 않고 <태그> 형태로 새로 만들기 때문에
// 속성(onclick, href 등)이 끼어들 틈이 없다 → 미리보기 렌더에 안전.
// (기존 sanitize.ts는 태그 전부 제거용이라 목적이 달라 별도 모듈로 둔다)

/** 본문에 허용하는 구조 태그. 링크(a)·이미지(img)는 v1에서 의도적으로 제외. */
const ALLOWED_TAGS = new Set([
  "h2", "h3", "h4",
  "p", "br", "hr",
  "ul", "ol", "li",
  "strong", "em", "b", "i",
  "blockquote",
]);

/** 내용까지 통째로 위험한 블록(스크립트류)은 여는 태그~닫는 태그를 함께 제거 */
const DROP_WITH_CONTENT = /<(script|style|iframe|object|embed|svg|math|form|textarea)\b[\s\S]*?<\/\1\s*>/gi;

const MAX_HTML_LEN = 30_000;

/** C0 제어문자 제거(개행·탭은 보존) */
function stripControl(input: string): string {
  let out = "";
  for (const ch of input) {
    const code = ch.codePointAt(0) ?? 0;
    const isControl =
      (code <= 0x1f && code !== 0x09 && code !== 0x0a && code !== 0x0d) || code === 0x7f;
    if (!isControl) out += ch;
  }
  return out;
}

/** 본문 HTML 정화 — 허용 태그만 속성 없이 재조립, 나머지 태그는 삭제. */
export function sanitizeWpHtml(input: unknown, maxLen = MAX_HTML_LEN): string {
  if (typeof input !== "string") return "";

  let s = input.replace(DROP_WITH_CONTENT, "").replace(/<!--[\s\S]*?-->/g, "");

  s = s.replace(/<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/g, (_m, slash: string, tag: string) => {
    const t = tag.toLowerCase();
    if (!ALLOWED_TAGS.has(t)) return "";
    if (t === "br" || t === "hr") return slash ? "" : `<${t}/>`;
    return slash ? `</${t}>` : `<${t}>`;
  });

  s = stripControl(s).trim();
  if (s.length > maxLen) s = s.slice(0, maxLen);
  return s;
}

/** HTML → 순수 텍스트(요약 fallback, 글자 수 계산용) */
export function wpHtmlToText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}
