// lib/pipeline/channels/index.ts — 채널 생성기 레지스트리 + 디스패치.
// §15.6: blog. §15.7에서 threads/instagram/cafe/shorts 추가.

import type { Channel, Core } from "@/lib/multipublish/types";
import { generateBlog } from "./blog";
import type { ChannelContext, ChannelGenResult } from "./types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyGenerator = (core: Core, ctx: ChannelContext) => Promise<ChannelGenResult<any>>;

// §15.7에서 4채널 추가 예정. 등록되지 않은 채널 요청은 워커가 partial로 처리.
const GENERATORS: Partial<Record<Channel, AnyGenerator>> = {
  blog: generateBlog,
};

export interface AnyChannelResult {
  content: unknown;
  costUsd: number;
  mocked: boolean;
}

/** 채널 1개 생성. 미구현 채널은 예외(워커가 partial로 처리). */
export async function generateChannel(
  channel: Channel,
  core: Core,
  ctx: ChannelContext,
): Promise<AnyChannelResult> {
  const gen = GENERATORS[channel];
  if (!gen) throw new Error(`채널 미구현: ${channel}`);
  return gen(core, ctx);
}

export function implementedChannels(): Channel[] {
  return Object.keys(GENERATORS) as Channel[];
}
