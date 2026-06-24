// lib/pipeline/channels/cafe.ts — 카페 생성 (스펙 §7, Haiku).
// 커뮤니티 톤, 광고티 제거, 댓글 유도 1줄.

import { generate, safeParseJson } from "@/lib/gateway";
import type { CafeContent, Core } from "@/lib/multipublish/types";
import { SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { sanitizeBody, sanitizeLine } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

function system(ctx: ChannelContext): string {
  return `너는 네이버 카페 같은 커뮤니티에 글을 올리는 일반 이용자다. 아래 코어로 자연스러운 커뮤니티 글을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

[포맷/톤]
- title: 커뮤니티 글 제목(낚시 X, 솔직하게).
- body: 본문. 광고·홍보 티를 빼고 실제 경험·정보 공유하듯. "~했어요/~하더라고요" 같은 구어체. 과한 마케팅 문구 금지.
- comment_bait: 댓글을 유도하는 자연스러운 한 줄("다들 어떻게 하세요?" 류).

[규칙]
${SAFETY_RULES}
- 광고처럼 보이면 실패다. 정보/경험 공유가 본질.
- ${monetizeHint(ctx.options)} 단, 카페에서는 노골적 홍보 금지.
- 톤: ${toneLabel(ctx.options.tone)}, 단 커뮤니티 눈높이.

스키마: { "title":"", "body":"", "comment_bait":"" }`;
}

export async function generateCafe(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"cafe">> {
  const res = await generate({
    task: "channel.cafe",
    system: system(ctx),
    input: JSON.stringify({ keyword: ctx.keyword, core }),
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<CafeContent>>(res.text);
  return { content: normalize(parsed, core, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<CafeContent>, core: Core, ctx: ChannelContext): CafeContent {
  const k = ctx.keyword || "주제";
  return {
    title: sanitizeLine(parsed.title, 120) || `${k} 해보신 분들 계세요? 후기 공유해요`,
    body: sanitizeBody(parsed.body, 4000) || `${core.core_message}\n\n저는 이렇게 해봤는데 다들 어떠신지 궁금해요.`,
    comment_bait: sanitizeLine(parsed.comment_bait, 200) || "다들 어떻게 하시는지 댓글로 알려주세요!",
  };
}

function mock(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "주제";
  return JSON.stringify({
    title: `${k} 처음 해보는데 이렇게 하는 거 맞나요?`,
    body: `요즘 ${k}에 관심이 생겨서 이것저것 찾아봤어요.\n\n${core.core_message}\n\n${core.angles[0] ?? "기본기"}가 중요하다고 하더라고요. 저처럼 막 시작하는 분들께 도움이 될까 해서 정리해봤어요.`,
    comment_bait: "혹시 더 좋은 방법 아시는 분 댓글로 알려주실 수 있나요?",
  });
}
