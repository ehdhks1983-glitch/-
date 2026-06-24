// lib/pipeline/channels/threads.ts — 스레드 생성 (스펙 §7, Haiku).
// 연결 체인 3~6개(1=훅→본문→CTA), 해시태그 0~2. 자연스러움·구체성 우선(§NATURALNESS).

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, ThreadsContent } from "@/lib/multipublish/types";
import { BANNED_CLICHES, MOCK_NOTICE, NATURALNESS, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { dedupeTags, sanitizeTag, strList } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

function system(ctx: ChannelContext): string {
  return `너는 스레드(Threads)를 잘 쓰는 사람이다. 아래 코어로 '연결된 짧은 글 체인'을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

${NATURALNESS}

[포맷]
- posts: 3~6개의 짧은 글 배열. 1번=첫 줄에서 멈추게 만드는 훅, 중간=한 편당 메시지 하나(구체적으로, 280자 내외), 마지막=가벼운 행동 유도.
- hashtags: 0~2개(해시 # 없이, 꼭 필요할 때만). 키워드 변형 도배 금지.

[규칙]
${BANNED_CLICHES}
${SAFETY_RULES}
- 매 글에 키워드를 박지 마라. 주제는 자연스럽게 흐르게.
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}. 이모지는 한두 개만.

스키마: { "posts":["",""], "hashtags":[] }`;
}

export async function generateThreads(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"threads">> {
  const res = await generate({
    task: "channel.threads",
    system: system(ctx),
    input: `주제: ${ctx.keyword}\n\ncore:\n${JSON.stringify(core)}`,
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<ThreadsContent>>(res.text);
  return { content: normalize(parsed, core), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<ThreadsContent>, core: Core): ThreadsContent {
  let posts = strList(parsed.posts, 6, 320);
  if (posts.length < 1) {
    posts = [
      "막상 시작하면 다들 비슷한 데서 막히더라고요. 시행착오 줄이는 포인트만 짧게 🧵",
      core.core_message,
      "도움 됐으면 저장해두고, 더 궁금한 건 댓글로!",
    ];
  }
  const hashtags = dedupeTags((Array.isArray(parsed.hashtags) ? parsed.hashtags : []).map(sanitizeTag).filter(Boolean)).slice(0, 2);
  return { posts, hashtags };
}

/** 키리스 목: 첫 글 상단에 체험 고지 + 키워드 도배 없이 자연스러운 체인. */
function mock(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "이 주제";
  return JSON.stringify({
    posts: [
      `${MOCK_NOTICE}\n\n${k}, 막상 시작하면 다들 비슷한 데서 막히더라고요 🧵`,
      "오늘은 시행착오를 줄이는 포인트만 짧게 정리해볼게요.",
      "먼저 준비물과 순서부터. 여기서 시간이 제일 많이 갈립니다.",
      "흔한 실수 하나 더 — 남들 기준 말고 내 조건부터 챙기기. 이유를 알면 안 하게 돼요.",
      "도움 됐으면 저장! 더 궁금한 건 댓글로 물어보세요.",
    ],
    hashtags: [k, "꿀팁"],
  });
}
