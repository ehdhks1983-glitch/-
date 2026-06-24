// lib/scraper/extract.ts — cheerio 기반 본문 추출(순수 함수, 네트워크 무관 → 단위 테스트 용이).
// 셀렉터 폴백 체인을 순서대로 시도하고 가장 긴 본문을 채택. 블록 태그는 줄바꿈으로 보존.

import * as cheerio from "cheerio";
import type { CheerioAPI, Cheerio } from "cheerio";
import type { AnyNode } from "domhandler";

/** 잡음 요소(스크립트/네비/댓글/광고 등) 제거 후 본문 후보를 평가. */
const JUNK_SELECTOR =
  "script,style,noscript,template,svg,form,nav,header,footer,aside,iframe,.u_cbox,.comment,#comment,.ad,.advertisement,.reply,.sns";

/** 공백류 정규화 대상: 스페이스/탭/NBSP/제로폭/전각공백. */
const WS = /[ \t ​　]+/g;

export interface ExtractResult {
  text: string;
  selector?: string;
}

/** 블록 종료 태그를 줄바꿈으로 바꿔 문단 구조를 살린 뒤 텍스트만 추출. */
function blockText($: CheerioAPI, el: Cheerio<AnyNode>): string {
  const html = $.html(el) ?? "";
  const withBreaks = html
    .replace(/<\/(p|div|li|h[1-6]|blockquote|tr|section|article)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n");
  return clean(cheerio.load(withBreaks).root().text());
}

/** 줄 단위 공백 정리 + 빈 줄 축약. */
export function clean(s: string): string {
  return s
    .split("\n")
    .map((l) => l.replace(WS, " ").trim())
    .filter(Boolean)
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * 셀렉터 폴백 체인으로 본문 추출. 가장 텍스트가 긴 후보 채택.
 * 모두 부실하면 body 전체로 폴백.
 */
export function extractText(html: string, selectors: string[]): ExtractResult {
  const $ = cheerio.load(html);
  $(JUNK_SELECTOR).remove();

  let best: ExtractResult = { text: "" };
  for (const sel of selectors) {
    const el = $(sel).first();
    if (!el.length) continue;
    const t = blockText($, el);
    if (t.length > best.text.length) best = { text: t, selector: sel };
  }

  if (best.text.length < 50) {
    const bodyText = blockText($, $("body").first());
    if (bodyText.length > best.text.length) best = { text: bodyText, selector: "body" };
  }
  return best;
}

/** 제목 추출(og:title → <title> → h1). generation.title 기본값에 사용. */
export function extractTitle(html: string): string {
  const $ = cheerio.load(html);
  const og = $('meta[property="og:title"]').attr("content");
  const title = og || $("title").first().text() || $("h1").first().text();
  return clean(title || "").slice(0, 200);
}
