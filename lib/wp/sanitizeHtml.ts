// lib/wp/sanitizeHtml.ts  [업데이트 — 워드프레스 자동 발행 v2]
// AI가 만든 본문 HTML 정화. 허용 태그만 "재조립"해서 내보낸다:
// 통과한 태그도 원문을 그대로 쓰지 않고 <태그> 형태로 새로 만들기 때문에
// 속성(onclick, style 등)이 끼어들 틈이 없다 → 미리보기 렌더에 안전.
// v2: 내부 링크(allowLinkHosts 에 포함된 호스트의 http(s) 주소)만 <a href> 로 허용한다.
// 외부 링크·javascript: 등은 태그만 벗기고 글자는 남긴다.

/** 본문에 허용하는 구조 태그. 이미지(img)는 대표 이미지(featured_media)로만 다룬다. */
const ALLOWED_TAGS = new Set([
  "h2", "h3", "h4",
  "p", "br", "hr",
  "ul", "ol", "li",
  "strong", "em", "b", "i",
  "blockquote",
]);

/** 내용까지 통째로 위험한 블록(스크립트류)은 여는 태그~닫는 태그를 함께 제거 */
const DROP_WITH_CONTENT = /<(script|style|iframe|object|embed|svg|math|form|textarea)\b[\s\S]*?<\/\1\s*>/gi;

const TAG_RE = /<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
const HREF_RE = /href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i;

const MAX_HTML_LEN = 30_000;

export interface SanitizeOptions {
  maxLen?: number;
  /** 이 호스트들(www. 제외, 소문자)로 향하는 링크만 허용. 비우면 링크 전부 제거 */
  allowLinkHosts?: string[];
}

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

function unescapeAttr(v: string): string {
  return v.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
}

function escapeAttr(v: string): string {
  return v.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** 사이트 주소 → 링크 허용 비교용 호스트("www." 제거, 소문자). 잘못된 주소면 null */
export function siteHostOf(siteUrl: string): string | null {
  try {
    return normalizeHost(new URL(siteUrl).hostname);
  } catch {
    return null;
  }
}

function normalizeHost(host: string): string {
  return host.toLowerCase().replace(/^www\./, "");
}

/** 허용 호스트의 http(s) 링크면 정규화된 주소, 아니면 null */
function safeLinkHref(raw: string, hosts: string[]): string | null {
  if (hosts.length === 0) return null;
  let u: URL;
  try {
    u = new URL(unescapeAttr(raw).trim());
  } catch {
    return null;
  }
  if (u.protocol !== "https:" && u.protocol !== "http:") return null;
  if (u.username || u.password) return null;
  const host = normalizeHost(u.hostname);
  return hosts.includes(host) ? u.href : null;
}

/** 본문 HTML 정화 — 허용 태그만 속성 없이 재조립, 링크는 내부 링크만, 나머지 태그는 삭제. */
export function sanitizeWpHtml(input: unknown, opts: SanitizeOptions = {}): string {
  if (typeof input !== "string") return "";
  const maxLen = opts.maxLen ?? MAX_HTML_LEN;
  const hosts = (opts.allowLinkHosts ?? []).map(normalizeHost);

  let s = input.replace(DROP_WITH_CONTENT, "").replace(/<!--[\s\S]*?-->/g, "");

  let openLinks = 0;
  s = s.replace(TAG_RE, (_m, slash: string, tag: string, attrs: string) => {
    const t = tag.toLowerCase();

    if (t === "a") {
      if (slash) {
        if (openLinks > 0) {
          openLinks--;
          return "</a>";
        }
        return "";
      }
      const h = attrs.match(HREF_RE);
      const href = h ? safeLinkHref(h[1] ?? h[2] ?? h[3] ?? "", hosts) : null;
      if (!href) return "";
      openLinks++;
      return `<a href="${escapeAttr(href)}">`;
    }

    if (!ALLOWED_TAGS.has(t)) return "";
    if (t === "br" || t === "hr") return slash ? "" : `<${t}/>`;
    return slash ? `</${t}>` : `<${t}>`;
  });
  while (openLinks-- > 0) s += "</a>";

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
