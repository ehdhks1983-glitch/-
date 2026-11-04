// lib/wp/blocks.ts  [신규 — 워드프레스 자동 발행 v2]
// 정화된 HTML → 블록 에디터(구텐베르크) 직렬화 마크업.
// REST API로 HTML만 보내면 WP가 "클래식" 콘텐츠로 저장해 블록 편집이 불편하다(조사 반영).
// 형식은 Gutenberg 공식 테스트 픽스처(test/integration/fixtures/blocks) 기준:
//   <!-- wp:heading {"level":3} --><h3 class="wp-block-heading">…</h3><!-- /wp:heading -->
//   <!-- wp:list --><ul class="wp-block-list"><!-- wp:list-item --><li>…</li><!-- /wp:list-item --></ul><!-- /wp:list -->
//   <!-- wp:quote --><blockquote class="wp-block-quote"><!-- wp:paragraph -->…<!-- /wp:paragraph --></blockquote><!-- /wp:quote -->
// 입력은 sanitizeWpHtml 을 거친 HTML(허용 태그 + 내부 링크 a href)만 가정한다.

interface ElNode {
  type: "el";
  tag: string;
  href?: string;
  children: Node[];
}
interface TextNode {
  type: "text";
  text: string;
}
type Node = ElNode | TextNode;

const VOID_TAGS = new Set(["br", "hr"]);
const BLOCK_TAGS = new Set(["h2", "h3", "h4", "p", "ul", "ol", "li", "blockquote", "hr"]);
const INLINE_ALIAS: Record<string, string> = { b: "strong", i: "em" };

const TOKEN_RE = /<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>|([^<]+)|(<)/g;

function unescapeAttr(v: string): string {
  return v.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
}

function escapeAttr(v: string): string {
  return v.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** 관대한 파서: 닫히지 않은 태그는 부모가 닫힐 때 함께 닫고, 짝 없는 닫는 태그는 무시한다. */
function parse(html: string): Node[] {
  const root: ElNode = { type: "el", tag: "#root", children: [] };
  const stack: ElNode[] = [root];
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(html))) {
    if (m[4] !== undefined || m[5] !== undefined) {
      stack[stack.length - 1].children.push({ type: "text", text: m[4] ?? m[5] });
      continue;
    }
    const closing = m[1] === "/";
    const tag = m[2].toLowerCase();
    const attrs = m[3] ?? "";
    if (closing) {
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tag === tag) {
          stack.length = i;
          break;
        }
      }
      continue;
    }
    const node: ElNode = { type: "el", tag, children: [] };
    if (tag === "a") {
      const h = attrs.match(/href\s*=\s*"([^"]*)"/i);
      if (h) node.href = unescapeAttr(h[1]);
    }
    stack[stack.length - 1].children.push(node);
    if (!VOID_TAGS.has(tag) && !/\/\s*$/.test(attrs)) stack.push(node);
  }
  return root.children;
}

/** 인라인 직렬화: 텍스트 + strong/em/a/br. 블록 태그가 섞여 들어오면 내용만 펼친다. */
function inline(nodes: Node[]): string {
  let out = "";
  for (const n of nodes) {
    if (n.type === "text") {
      out += n.text;
      continue;
    }
    const tag = INLINE_ALIAS[n.tag] ?? n.tag;
    if (tag === "br") {
      out += "<br>";
      continue;
    }
    if (tag === "a") {
      out += n.href ? `<a href="${escapeAttr(n.href)}">${inline(n.children)}</a>` : inline(n.children);
      continue;
    }
    if (tag === "strong" || tag === "em") {
      out += `<${tag}>${inline(n.children)}</${tag}>`;
      continue;
    }
    out += inline(n.children);
  }
  return out;
}

const paragraph = (s: string) => `<!-- wp:paragraph -->\n<p>${s}</p>\n<!-- /wp:paragraph -->`;

const heading = (level: number, s: string) =>
  `<!-- wp:heading${level === 2 ? "" : ` {"level":${level}}`} -->\n<h${level} class="wp-block-heading">${s}</h${level}>\n<!-- /wp:heading -->`;

const SEPARATOR =
  '<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n<!-- /wp:separator -->';

const listItem = (s: string, nested: string) =>
  `<!-- wp:list-item -->\n<li>${s}${nested}</li>\n<!-- /wp:list-item -->`;

function list(node: ElNode): string {
  const ordered = node.tag === "ol";
  const items: string[] = [];
  let stray: Node[] = [];
  const flushStray = () => {
    const s = inline(stray).trim();
    stray = [];
    if (s) items.push(listItem(s, ""));
  };

  for (const c of node.children) {
    if (c.type === "el" && c.tag === "li") {
      flushStray();
      const inlineNodes: Node[] = [];
      const nested: string[] = [];
      for (const cc of c.children) {
        if (cc.type === "el" && (cc.tag === "ul" || cc.tag === "ol")) nested.push(list(cc));
        else if (cc.type === "el" && cc.tag === "p") inlineNodes.push(...cc.children);
        else inlineNodes.push(cc);
      }
      const text = inline(inlineNodes).trim();
      const inner = nested.filter(Boolean).join("");
      if (text || inner) items.push(listItem(text, inner));
    } else if (c.type === "el" && (c.tag === "ul" || c.tag === "ol")) {
      flushStray();
      const inner = list(c);
      if (inner) items.push(listItem("", inner));
    } else {
      stray.push(c);
    }
  }
  flushStray();
  if (items.length === 0) return "";

  const tag = ordered ? "ol" : "ul";
  return `<!-- wp:list${ordered ? ' {"ordered":true}' : ""} -->\n<${tag} class="wp-block-list">${items.join("\n\n")}</${tag}>\n<!-- /wp:list -->`;
}

function quote(node: ElNode): string {
  const inner = serializeBlocks(node.children).filter(Boolean);
  if (inner.length === 0) return "";
  return `<!-- wp:quote -->\n<blockquote class="wp-block-quote">${inner.join("\n\n")}</blockquote>\n<!-- /wp:quote -->`;
}

function serializeBlocks(nodes: Node[]): string[] {
  const blocks: string[] = [];
  let pending: Node[] = [];
  const flush = () => {
    const s = inline(pending).trim();
    pending = [];
    if (s && s !== "<br>") blocks.push(paragraph(s));
  };

  for (const n of nodes) {
    if (n.type === "text" || !BLOCK_TAGS.has(n.tag)) {
      if (n.type === "text" && !n.text.trim() && pending.length === 0) continue; // 블록 사이 공백
      pending.push(n);
      continue;
    }
    flush();
    switch (n.tag) {
      case "p": {
        const s = inline(n.children).trim();
        if (s) blocks.push(paragraph(s));
        break;
      }
      case "h2":
      case "h3":
      case "h4": {
        const s = inline(n.children).trim();
        if (s) blocks.push(heading(Number(n.tag[1]), s));
        break;
      }
      case "ul":
      case "ol":
        blocks.push(list(n));
        break;
      case "li":
        blocks.push(list({ type: "el", tag: "ul", children: [n] }));
        break;
      case "blockquote":
        blocks.push(quote(n));
        break;
      case "hr":
        blocks.push(SEPARATOR);
        break;
    }
  }
  flush();
  return blocks.filter(Boolean);
}

/** 정화된 HTML → 블록 에디터 마크업. 블록 사이는 빈 줄로 구분(코어 직렬화와 동일). */
export function htmlToBlocks(html: string): string {
  return serializeBlocks(parse(html)).join("\n\n");
}

/** 블록 개수(간단 통계용) */
export function countBlocks(blockMarkup: string): number {
  return (blockMarkup.match(/<!-- wp:(?!list-item)[a-z]+/g) ?? []).length;
}
