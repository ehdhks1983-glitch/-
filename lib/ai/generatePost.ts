// lib/ai/generatePost.ts  [신규 — 워드프레스 자동 발행]
// 주제/키워드 → 워드프레스에 바로 올릴 블로그 글(제목·본문HTML·요약·태그).
// 기존 폴백 체인(core.ts)을 그대로 타므로 키가 없으면 목 응답으로 동작한다.

import { withFallback, safeParseJson } from "./core";
import { sanitizeText } from "@/lib/sanitize";
import { sanitizeWpHtml, wpHtmlToText } from "@/lib/wp/sanitizeHtml";
import type { GeneratedPost, PostGenInput } from "@/lib/wp/types";

const LENGTH_GUIDE: Record<PostGenInput["length"], string> = {
  short: "공백 포함 600~900자 (가볍게 읽는 글)",
  medium: "공백 포함 1,200~1,800자 (표준 블로그 글)",
  long: "공백 포함 2,000~3,000자 (깊이 있는 정보 글)",
};

const LIMITS = {
  title: 120,
  excerpt: 200,
  tag: 50,
  maxTags: 8,
  minBodyChars: 50,
};

function buildSystem(input: PostGenInput): string {
  return `너는 검색 상위 노출 경험이 많은 한국어 블로그 전문 작가다. 주어진 주제로 워드프레스에 바로 올릴 글을 쓴다.
JSON 객체 하나만 출력한다. 설명·마크다운·코드펜스 없이 순수 JSON만.

[글쓰기 원칙]
- 제목: 핵심 키워드를 포함해 30자 안팎. 읽을 이유가 보이게, 낚시·과장 금지.
- 구조: 짧은 도입(문제 공감/왜 중요한지) → h2/h3 소제목으로 나눈 본문 → 핵심 정리 마무리.
- 문단은 2~4문장으로 짧게. 나열되는 정보는 ul/ol 리스트로 정리.
- 지어낸 수치·통계·후기·최신 뉴스 인용 금지. 일반적으로 알려진 사실과 실용 팁 위주로.
- "오늘은 ~에 대해 알아보겠습니다"류 상투 도입, 같은 말 반복 금지. 사람이 쓴 듯 자연스럽게.

[안전 규칙]
- 의료·법률·금융 주제는 단정 대신 일반 정보 수준으로 쓰고 전문가 상담을 권한다.
- 효능·수익 보장 표현("100% 치료", "무조건 수익") 금지. 전문가 사칭 금지.

[본문 HTML 규칙]
- 허용 태그: h2 h3 p ul ol li strong em blockquote 만. 링크(a)·이미지·그 외 태그·속성 금지.
- h1은 쓰지 않는다(제목이 h1이 된다).

[분량] ${LENGTH_GUIDE[input.length]}
[톤] ${input.tone || "친절하고 신뢰감 있는 정보 전달형"}
${input.categoryName ? `[카테고리] "${input.categoryName}" 카테고리 성격에 맞게 쓴다.` : ""}

스키마(그대로 따를 것):
{"title":"","html":"","excerpt":"","tags":["",""]}
- excerpt: 검색 결과·목록에 보일 120자 이내 요약. 본문 복붙 금지.
- tags: 검색에 쓰일 핵심 키워드 3~6개(각 1~3단어).`;
}

function buildUser(input: PostGenInput): string {
  const payload: Record<string, string> = { 주제_키워드: input.topic };
  if (input.extra) payload.추가_요청사항 = input.extra;
  return JSON.stringify(payload, null, 2);
}

/** 주제 → 발행 가능한 글 초안. 결과는 전부 정화를 거친다. */
export async function generatePost(input: PostGenInput): Promise<GeneratedPost> {
  const raw = await withFallback("post", {
    system: buildSystem(input),
    user: buildUser(input),
    json: true,
  });

  const p = safeParseJson<Partial<GeneratedPost>>(raw);

  const html = sanitizeWpHtml(p.html);
  const bodyText = wpHtmlToText(html);
  if (bodyText.length < LIMITS.minBodyChars) {
    throw new Error("생성된 본문이 너무 짧아요. 주제를 조금 더 구체적으로 적어 주세요.");
  }

  const title = sanitizeText(p.title, LIMITS.title) || sanitizeText(input.topic, LIMITS.title);
  const excerpt =
    sanitizeText(p.excerpt, LIMITS.excerpt) || `${bodyText.slice(0, 110)}…`;
  const tags = Array.isArray(p.tags)
    ? p.tags
        .map((t) => sanitizeText(t, LIMITS.tag))
        .filter(Boolean)
        .slice(0, LIMITS.maxTags)
    : [];

  return { title, html, excerpt, tags };
}
