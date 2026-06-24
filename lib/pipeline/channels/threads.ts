// lib/pipeline/channels/threads.ts — 스레드 생성 (스펙 §7, Haiku).
// 연결 체인 3~6개(1=훅→본문→CTA), 해시태그 0~2.

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, ThreadsContent } from "@/lib/multipublish/types";
import { BANNED_CLICHES, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { dedupeTags, sanitizeTag, strList } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

function system(ctx: ChannelContext): string {
  return `너는 스레드(Threads) 작가다. 아래 코어로 '연결된 짧은 글 체인'을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

[포맷]
- posts: 3~6개의 짧은 글 배열. 1번=강한 훅(첫 줄에서 멈추게), 중간=핵심 본문(한 편당 1메시지, 280자 내외), 마지막=행동 유도(CTA).
- hashtags: 0~2개(해시 # 없이, 꼭 필요할 때만).

[규칙]
${BANNED_CLICHES}
${SAFETY_RULES}
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}. 이모지는 과하지 않게.

스키마: { "posts":["",""], "hashtags":[] }`;
}

export async function generateThreads(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"threads">> {
  const res = await generate({
    task: "channel.threads",
    system: system(ctx),
    input: JSON.stringify({ keyword: ctx.keyword, core }),
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<ThreadsContent>>(res.text);
  return { content: normalize(parsed, core, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<ThreadsContent>, core: Core, ctx: ChannelContext): ThreadsContent {
  let posts = strList(parsed.posts, 6, 320);
  if (posts.length < 1) {
    posts = [
      `${ctx.keyword}, 이거 모르면 손해예요 🧵`,
      core.core_message,
      "도움 됐다면 저장 + 팔로우 부탁해요!",
    ];
  }
  const hashtags = dedupeTags((Array.isArray(parsed.hashtags) ? parsed.hashtags : []).map(sanitizeTag).filter(Boolean)).slice(0, 2);
  return { posts, hashtags };
}

function mock(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "주제";
  return JSON.stringify({
    posts: [
      `${k}, 처음엔 다들 여기서 막혀요 🧵`,
      core.core_message,
      `핵심은 이거예요 → ${core.angles[0] ?? "기본기"}`,
      `${core.angles[1] ?? "흔한 실수"}만 피해도 절반은 성공.`,
      "도움 됐다면 저장하고 팔로우해요. 다음 편에서 더 깊게!",
    ],
    hashtags: [k, "꿀팁"],
  });
}
