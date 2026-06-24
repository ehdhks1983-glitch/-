// lib/pipeline/channels/blog.ts — 블로그 생성 (스펙 §7, Sonnet). SEO 포맷 + 핵심태그 정확히 10개(§13/§16).
// 태그 10개·썸네일 1:1 등 콘텐츠 룰은 코드로 강제(모델 출력을 신뢰하지 않음).

import { generate, safeParseJson } from "@/lib/gateway";
import type { BlogContent, Core } from "@/lib/multipublish/types";
import { BANNED_CLICHES, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { dedupeTags, sanitizeBody, sanitizeLine, sanitizeTag } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

/** 블로그 핵심 태그 개수 — 스펙 §13/§16 "정확히 10개". */
export const BLOG_TAG_COUNT = 10;

function system(ctx: ChannelContext): string {
  return `너는 SEO에 강한 한국어 블로그 작가다. 아래 코어(core)를 바탕으로 검색 노출과 가독성을 모두 잡는 블로그 글을 JSON 객체 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

[SEO/포맷]
- title: 키워드를 자연스럽게 포함한 제목(낚시·과장 금지, 32자 내외).
- meta_description: 검색 결과 요약용 1~2문장(150자 내외, 키워드 포함).
- body_markdown: 마크다운. 도입(공감) → ## 소제목 여러 개(리스트/단계 포함) → 마무리(요약+행동 제안). 키워드와 연관어 자연 배치. 800~1500자.
- tags: 핵심 태그 정확히 ${BLOG_TAG_COUNT}개(해시 # 없이). core.tag_candidates에서 우선 고르고 부족하면 연관어로 채운다.
- thumbnail_guide: 썸네일 이미지 가이드 1~2문장. 비율은 반드시 1:1(정사각형).

[콘텐츠 룰]
${BANNED_CLICHES}
${SAFETY_RULES}
- 본문 사실은 core.facts 범위 내에서만. core.facts가 비어 있으면 단정적 수치 대신 일반적 설명/경험 위주.
- ${monetizeHint(ctx.options)}
- 사람이 쓴 듯 자연스럽게. 톤: ${toneLabel(ctx.options.tone)}

[출력 전 자가 점검] 1) tags 정확히 ${BLOG_TAG_COUNT}개 2) 효능 단정 없음 3) core.facts 밖 수치 없음 4) 도입-본문-마무리 흐름

스키마:
{ "title":"", "meta_description":"", "body_markdown":"", "tags":["10개"], "thumbnail_guide":"" }`;
}

function buildInput(core: Core, ctx: ChannelContext): string {
  return JSON.stringify({ keyword: ctx.keyword, core });
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
  const k = ctx.keyword || "주제";
  return {
    title: sanitizeLine(parsed.title, 120) || `${k} 완벽 가이드`,
    meta_description: sanitizeLine(parsed.meta_description, 220) || core.core_message,
    body_markdown:
      sanitizeBody(parsed.body_markdown, 12000) || `## ${k}\n\n${core.core_message}`,
    tags: exactlyTen(parsed.tags, core, k),
    thumbnail_guide:
      sanitizeLine(parsed.thumbnail_guide, 300) ||
      `1:1 정사각형 썸네일. '${k}' 키워드를 큼직한 텍스트로, 배경은 단색 + 포인트 컬러.`,
  };
}

/** 태그를 항상 정확히 10개로 강제(부족하면 후보/연관어로 채우고, 많으면 자른다). */
export function exactlyTen(raw: unknown, core: Core, keyword: string): string[] {
  const fromModel = dedupeTags((Array.isArray(raw) ? raw : []).map(sanitizeTag).filter(Boolean));
  if (fromModel.length >= BLOG_TAG_COUNT) return fromModel.slice(0, BLOG_TAG_COUNT);

  const pool = dedupeTags([
    ...fromModel,
    ...core.tag_candidates.map(sanitizeTag).filter(Boolean),
    ...fallbackTags(keyword),
  ]);
  const filled = pool.slice(0, BLOG_TAG_COUNT);

  // 그래도 부족하면 키워드 변형으로 채운다(항상 10개 보장).
  let i = 1;
  while (filled.length < BLOG_TAG_COUNT) {
    const t = sanitizeTag(`${keyword}${i++}`);
    if (t && !filled.includes(t)) filled.push(t);
  }
  return filled.slice(0, BLOG_TAG_COUNT);
}

function fallbackTags(k: string): string[] {
  return [k, `${k}추천`, `${k}초보`, `${k}팁`, `${k}가이드`, `${k}방법`, `${k}후기`, `${k}정리`, `${k}비교`, `${k}입문`, `${k}꿀팁`, `${k}정보`].map(sanitizeTag);
}

function mockBlog(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "주제";
  const factLine = core.facts[0]?.claim ? `\n\n> 참고: ${core.facts[0].claim}` : "";
  return JSON.stringify({
    title: `${k} 완벽 가이드: 핵심만 빠르게`,
    meta_description: `${core.core_message} ${k} 초보도 따라 할 수 있게 단계별로 정리했어요.`,
    body_markdown: `${k}, 어디서부터 시작해야 할지 막막하셨죠? 이 글 하나면 충분합니다.

## ${k}, 왜 헷갈릴까
${core.core_message}

## 핵심 3가지
- ${core.angles[0] ?? "기본기부터"}
- ${core.angles[1] ?? "흔한 실수 피하기"}
- ${core.angles[2] ?? "체크리스트 활용"}${factLine}

## 마무리
오늘 정리한 내용만 지켜도 절반은 성공입니다. 천천히 하나씩 적용해 보세요.`,
    tags: core.tag_candidates.slice(0, 12),
    thumbnail_guide: `1:1 정사각형. '${k}'를 큰 텍스트로, 깔끔한 단색 배경 + 포인트 컬러 한 가지.`,
  });
}
