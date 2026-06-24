// lib/pipeline/channels/blog.ts — 블로그 생성 (스펙 §7, Sonnet). SEO 포맷 + 핵심태그 정확히 10개(§13/§16).
// 포맷: 본문 ==형광펜== 강조 + key_points(📌 핵심 정리, 가운데정렬) + 수익화 시 CTA 1개. 광고법 준수.
// 품질: 키워드 도배·일반론 금지, 그 주제만의 구체 내용(§NATURALNESS).

import { generate, safeParseJson } from "@/lib/gateway";
import type { BlogContent, Core } from "@/lib/multipublish/types";
import { BANNED_CLICHES, MOCK_NOTICE, NATURALNESS, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { dedupeTags, sanitizeBody, sanitizeLine, sanitizeTag, strList } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

/** 블로그 핵심 태그 개수 — 스펙 §13/§16 "정확히 10개". */
export const BLOG_TAG_COUNT = 10;

/** 태그가 모자랄 때 채우는 일반 콘텐츠 태그(키워드 변형 도배 회피용). */
const GENERIC_TAG_POOL = ["정보", "후기", "꿀팁", "가이드", "정리", "추천", "노하우", "비교", "입문", "초보", "주의사항", "체크리스트", "팁", "방법", "일상"];

function system(ctx: ChannelContext): string {
  const monetize = ctx.options.monetize;
  return `너는 해당 분야를 실제로 잘 아는 한국어 블로그 작가다. 아래 코어(core)를 바탕으로 검색에도 잘 잡히고 사람이 끝까지 읽는 블로그 글을 JSON 객체 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

${NATURALNESS}

[SEO·포맷]
- title: 주제를 자연스럽게 담은 제목(32자 내외, 낚시·과장 금지). 키워드를 어색하게 욱여넣지 마라.
- meta_description: 검색 결과 요약 1~2문장(150자 내외). 글을 클릭할 이유가 보이게.
- body_markdown: 마크다운. 도입(공감/문제 제기) → ## 소제목 여러 개(구체 단계·예시·리스트 포함) → 자연스러운 마무리. 800~1500자.
  · 정말 중요한 핵심 문구 2~4곳을 ==형광펜== 으로 감싼다(예: ==이것만 지켜도 절반은 성공==). 남발 금지.
- key_points: 글 맨 끝 "📌 핵심 정리"에 들어갈 한 줄 요약 3~5개(각 항목은 구체적이고 실행 가능하게).
- cta: ${monetize ? "독자가 다음 행동을 하도록 자연스러운 CTA 1줄(과장·단정 금지)." : "빈 문자열 \"\" (수익화 꺼짐)."}
- tags: 핵심 태그 정확히 ${BLOG_TAG_COUNT}개(해시 # 없이). '키워드+추천/초보/방법'식 변형 도배 금지 — 실제 연관어·세부주제·동의어로.
- thumbnail_guide: 썸네일 이미지 가이드 1~2문장. 비율은 반드시 1:1(정사각형).

[콘텐츠 룰]
${BANNED_CLICHES}
${SAFETY_RULES}
- 본문 사실은 core.facts 범위 내에서만. core.facts가 비어 있으면 단정적 수치 대신 일반적으로 통용되는 구체 예시·단계로.
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}. 사람이 직접 쓴 듯 자연스럽게.

[출력 전 자가 점검] 1) tags 정확히 ${BLOG_TAG_COUNT}개·키워드 도배 아님 2) 효능·수익 단정 없음 3) 일반론 아닌 구체 내용 4) ==형광펜== 2~4곳

스키마:
{ "title":"", "meta_description":"", "body_markdown":"", "key_points":["",""], "cta":"", "tags":["10개"], "thumbnail_guide":"" }`;
}

function buildInput(core: Core, ctx: ChannelContext): string {
  return `주제: ${ctx.keyword}\n\ncore:\n${JSON.stringify(core, null, 2)}`;
}

export async function generateBlog(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"blog">> {
  const res = await generate({
    task: "blog",
    system: system(ctx),
    input: buildInput(core, ctx),
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.9 : 0.7,
    mock: mockBlog(core, ctx),
  });
  const parsed = safeParseJson<Partial<BlogContent>>(res.text);
  return { content: normalizeBlog(parsed, core, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

export function normalizeBlog(parsed: Partial<BlogContent>, core: Core, ctx: ChannelContext): BlogContent {
  const k = ctx.keyword || "이 주제";
  return {
    title: sanitizeLine(parsed.title, 120) || defaultTitle(k),
    meta_description: sanitizeLine(parsed.meta_description, 220) || core.core_message,
    body_markdown: sanitizeBody(parsed.body_markdown, 12000) || core.core_message,
    key_points: strList(parsed.key_points, 5, 200),
    cta: ctx.options.monetize ? sanitizeLine(parsed.cta, 200) : "",
    tags: exactlyTen(parsed.tags, core, k),
    thumbnail_guide:
      sanitizeLine(parsed.thumbnail_guide, 300) ||
      `1:1 정사각형. 글의 핵심 한 줄을 큰 텍스트로, 단색 배경 + 포인트 컬러 하나로 깔끔하게.`,
  };
}

function defaultTitle(k: string): string {
  return `${k}, 시작 전에 알았으면 좋았을 것들`;
}

/** 태그를 항상 정확히 10개로 강제. 부족하면 코어 후보 → 일반 콘텐츠 태그로 채운다(키워드 변형 도배 금지). */
export function exactlyTen(raw: unknown, core: Core, keyword: string): string[] {
  const fromModel = dedupeTags((Array.isArray(raw) ? raw : []).map(sanitizeTag).filter(Boolean));
  if (fromModel.length >= BLOG_TAG_COUNT) return fromModel.slice(0, BLOG_TAG_COUNT);

  const pool = dedupeTags(
    [
      ...fromModel,
      ...core.tag_candidates.map(sanitizeTag),
      sanitizeTag(keyword),
      ...GENERIC_TAG_POOL,
    ].filter(Boolean),
  );
  return pool.slice(0, BLOG_TAG_COUNT);
}

/** 키리스 목: 키워드 도배 없이 자연스러운 자리표시 초안 + 체험 고지. */
function mockBlog(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "이 주제";
  const a = core.angles;
  const body = `${MOCK_NOTICE}

${k}, 검색해보면 정보는 많은데 막상 내 상황에 뭘 적용해야 할지 헷갈리죠. 처음 시작할 때 시행착오를 줄이는 쪽으로 짚어봤어요.

## 시작 전에 짚을 것
준비물과 순서를 먼저 확인하면 헤매는 시간이 확 줄어요. ==처음 방향만 제대로 잡아도 절반은 성공==입니다.

## 다들 한 번씩 하는 실수
- ${a[1] ?? "급하게 결정하다 비용을 더 쓰는 경우"}
- ${a[2] ?? "남들 말만 듣고 내 조건을 빼먹는 경우"}
이유를 알면 피하기 쉬워요.

## 현실적인 팁
예산·일정·인원 같은 내 조건부터 적어두고 비교하면 선택이 훨씬 수월해집니다.

## 마무리
완벽하게 하려다 시작을 못 하느니, 큰 것 몇 개만 챙기고 가볍게 출발하는 편이 나아요.`;
  return JSON.stringify({
    title: `${k}, 처음이라면 이것만 기억하세요`,
    meta_description: `${k}, 어디서부터 봐야 할지 막막한 분들을 위해 시작 전 체크포인트와 자주 하는 실수를 정리했어요.`,
    body_markdown: body,
    key_points: [
      "시작 전에 준비물·순서부터 확인하기",
      "남들 기준이 아니라 내 상황 기준으로 선택하기",
      "큰 것 몇 개만 챙기고 가볍게 시작하기",
    ],
    cta: ctx.options.monetize ? "더 자세한 비교가 필요하면 아래 정리 글도 함께 보세요." : "",
    tags: [k, "입문", "후기", "꿀팁", "정리", "추천", "노하우", "비교", "초보", "체크리스트"],
    thumbnail_guide: "1:1 정사각형. '시작 전 체크리스트' 같은 핵심 한 줄을 큰 글씨로, 단색 배경 + 포인트 컬러 하나.",
  });
}
