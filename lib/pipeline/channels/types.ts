// lib/pipeline/channels/types.ts — 채널 생성기 공통 타입.

import type { Channel, ChannelContent, Core, GenOptions } from "@/lib/multipublish/types";

export interface ChannelContext {
  keyword: string;
  options: GenOptions;
  /** 재생성이면 변형 다양성을 위해 temperature ↑ + 캐시 미사용. */
  regenerate?: boolean;
}

export interface ChannelGenResult<C extends Channel> {
  content: ChannelContent[C];
  costUsd: number;
  mocked: boolean;
}

export type ChannelGenerator<C extends Channel> = (
  core: Core,
  ctx: ChannelContext,
) => Promise<ChannelGenResult<C>>;
