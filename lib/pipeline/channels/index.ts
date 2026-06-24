// lib/pipeline/channels/index.ts — 채널 생성기 레지스트리 + 디스패치.
// 블로그(Sonnet) + 스레드/인스타/카페/쇼츠(Haiku). 입력은 모두 동일한 core.

import type { Channel, Core } from "@/lib/multipublish/types";
import { generateBlog } from "./blog";
import { generateThreads } from "./threads";
import { generateInstagram } from "./instagram";
import { generateCafe } from "./cafe";
import { generateShorts } from "./shorts";
import type { ChannelContext, ChannelGenResult } from "./types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyGenerator = (core: Core, ctx: ChannelContext) => Promise<ChannelGenResult<any>>;

const GENERATORS: Record<Channel, AnyGenerator> = {
  blog: generateBlog,
  threads: generateThreads,
  instagram: generateInstagram,
  cafe: generateCafe,
  shorts: generateShorts,
};

export interface AnyChannelResult {
  content: unknown;
  costUsd: number;
  mocked: boolean;
}

/** 채널 1개 생성. 미등록 채널은 예외(워커가 partial로 처리). */
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
