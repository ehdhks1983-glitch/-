// lib/ai/generatePost.ts  [업데이트 — 워드프레스 자동 발행 v2 (2026 기준 반영)]
// 주제/키워드 → 워드프레스에 바로 올릴 블로그 글(제목·본문HTML·요약·태그 + 슬러그·SEO 메타).
// 기존 폴백 체인(core.ts)을 그대로 타므로 키가 없으면 목 응답으로 동작한다.
// v2 반영 사항(조사):
//  - 검색엔진의 '대량 생산형 저품질 콘텐츠' 정책 → 구체 정보·독자 가치·FAQ 중심 프롬프트
//  - 글 유형(정보/리스트/리뷰/비교/경험담)별 구조 가이드
//  - 내 사이트 기존 글로의 내부 링크(허용 목록 안의 URL만)
//  - 영문 슬러그·SEO 제목·메타 설명·핵심 키워드 생성

import { withFallback, safeParseJson } from "./core";
import { sanitizeText } from "@/lib/sanitize";
import { sanitizeWpHtml, wpHtmlToText } from "@/lib/wp/sanitizeHtml";
import { POST_TYPES, type GeneratedPost, type PostGenInput } from "@/lib/wp/types";

const LENGTH_GUIDE: Record<PostGenInput["length"], string> = {
  short: "공백 포함 600~900자 (가볍게 읽는 글)",
  medium: "공백 포함 1,200~1,800자 (표준 블로그 글)",
  long: "공백 포함 2,000~3,000자 (깊이 있는 정보 글)",
};

const LIMITS = {
  title: 120,
  excerpt: 200,
  seoTitle: 70,
  metaDescription: 160,
  focusKeyword: 60,
  slug: 70,
  tag: 50,
  maxTags: 8,
  maxInternalLinks: 30,
  minBodyChars: 50,
};

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function buildSystem(input: PostGenInput): string {
  const type = POST_TYPES[input.postType ?? "info"];
  const links = (input.internalLinks ?? []).slice(0, LIMITS.maxInternalLinks);

  return `너는 검색 상위 노출 경험이 많은 한국어 블로그 전문 작가다. 주어진 주제로 워드프레스에 바로 올릴 글을 쓴다.
JSON 객체 하나만 출력한다. 설명·마크다운·코드펜스 없이 순수 JSON만.

[가장 중요한 원칙 — 독자에게 실제로 도움이 되는 글]
검색엔진은 생산 방식(AI/사람)과 무관하게 '독자 가치 없이 양만 늘린 글'을 스팸으로 분류한다. 따라서:
- 뻔한 일반론·분량 채우기 문장 금지. 구체적 절차·조건·수치 범위·주의점·예시·체크리스트처럼 '읽고 바로 써먹는 정보'로 채운다.
- 같은 말 반복 금지. 문단마다 새로운 정보가 있어야 한다.
- 경험·관찰·판단이 드러나는 문장을 1~2개 넣는다(단, 지어낸 수치·통계·후기·최신 뉴스 인용은 금지).
- 마지막에 h2 "자주 묻는 질문" 섹션을 두고 h3 질문 2~3개에 짧고 정확하게 답한다.

[글쓰기 원칙]
- 제목: 핵심 키워드를 포함해 30자 안팎. 읽을 이유가 보이게, 낚시·과장 금지.
- 구조: 짧은 도입(문제 공감/왜 중요한지, 첫 문단에 키워드 포함) → h2/h3 소제목으로 나눈 본문 → 핵심 정리.
- 문단은 2~4문장으로 짧게. 나열되는 정보는 ul/ol 리스트로 정리.
- "오늘은 ~에 대해 알아보겠습니다"류 상투 도입 금지. 사람이 쓴 듯 자연스럽게.

[글 유형: ${type.label}]
${type.guide}

[안전 규칙]
- 의료·법률·금융 주제는 단정 대신 일반 정보 수준으로 쓰고 전문가 상담을 권한다.
- 효능·수익 보장 표현("100% 치료", "무조건 수익") 금지. 전문가 사칭 금지.

[본문 HTML 규칙]
- 허용 태그: h2 h3 p ul ol li strong em blockquote 만. 이미지·그 외 태그·속성 금지. h1은 쓰지 않는다(제목이 h1이 된다).
${
  links.length
    ? `- 내부 링크: 아래 "기존 글" 중 이 주제와 정말 관련 있는 글 1~2개를 본문의 자연스러운 문장에 <a href="URL">앵커 문구</a> 형태로 연결한다. 목록에 없는 URL은 절대 만들지 않는다. 관련 글이 없으면 링크를 넣지 않는다.
기존 글:
${links.map((l) => `  - ${l.title} :: ${l.url}`).join("\n")}`
    : "- 링크(a)는 쓰지 않는다."
}

[분량] ${LENGTH_GUIDE[input.length]}
[톤] ${input.tone || "친절하고 신뢰감 있는 정보 전달형"}
${input.categoryName ? `[카테고리] "${input.categoryName}" 카테고리 성격에 맞게 쓴다.` : ""}

스키마(그대로 따를 것):
{"title":"","slug":"","seoTitle":"","metaDescription":"","focusKeyword":"","html":"","excerpt":"","tags":["",""]}
- slug: 영문 소문자·숫자·하이픈만, 3~6단어, 키워드의 영어 번역(예: "sme-government-grant-guide").
- seoTitle: 검색 결과 제목용 60자 이내(키워드 앞쪽 배치). metaDescription: 80~150자, 클릭할 이유가 보이게.
- focusKeyword: 글의 핵심 키워드 1개(주제어 그대로 또는 다듬어서).
- excerpt: 목록에 보일 120자 이내 요약. 본문 복붙 금지. tags: 핵심 키워드 3~6개(각 1~3단어).`;
}

function buildUser(input: PostGenInput): string {
  const payload: Record<string, unknown> = { 주제_키워드: input.topic };
  if (input.extra) payload.추가_요청사항 = input.extra;
  if (input.internalLinks?.length) {
    payload.기존_글_목록 = input.internalLinks
      .slice(0, LIMITS.maxInternalLinks)
      .map((l) => ({ title: l.title, url: l.url }));
  }
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

  const html = sanitizeWpHtml(p.html, {
    allowLinkHosts: input.siteHost ? [input.siteHost] : [],
  });
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

  const slugRaw = sanitizeText(p.slug, LIMITS.slug).toLowerCase();
  const slug = SLUG_RE.test(slugRaw) ? slugRaw : "";

  return {
    title,
    html,
    excerpt,
    tags,
    slug,
    seoTitle: sanitizeText(p.seoTitle, LIMITS.seoTitle) || title.slice(0, LIMITS.seoTitle),
    metaDescription: sanitizeText(p.metaDescription, LIMITS.metaDescription) || excerpt,
    focusKeyword: sanitizeText(p.focusKeyword, LIMITS.focusKeyword) || sanitizeText(input.topic, LIMITS.focusKeyword),
  };
}
