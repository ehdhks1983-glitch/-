// lib/multipublish/serialize.ts — 저장 모델 → 클라이언트 응답 모델.
// 채널은 채널별 최신 variant만, ALL_CHANNELS 순서로 정렬(탭 순서 안정).

import { latestOutputs, type StoredGeneration } from "@/lib/store/types";
import { ALL_CHANNELS, type Channel, type Core, type GenOptions, type GenerationStatus, type SourceRef } from "./types";

export interface ClientChannelOutput {
  channel: Channel;
  variant_no: number;
  status: "done" | "failed";
  content: unknown;
  error?: string;
}

export interface ClientGeneration {
  id: string;
  keyword: string;
  title: string;
  status: GenerationStatus;
  error: string | null;
  core: Core | null;
  options: GenOptions;
  source_refs: SourceRef[];
  channels: ClientChannelOutput[];
  starred: boolean;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export function toClientGeneration(rec: StoredGeneration): ClientGeneration {
  const order = (c: Channel) => ALL_CHANNELS.indexOf(c);
  const channels = latestOutputs(rec.outputs)
    .map((o) => ({
      channel: o.channel,
      variant_no: o.variant_no,
      status: o.status,
      content: o.content,
      error: o.error,
    }))
    .sort((a, b) => order(a.channel) - order(b.channel));

  return {
    id: rec.id,
    keyword: rec.keyword,
    title: rec.title,
    status: rec.status,
    error: rec.error,
    core: rec.core,
    options: rec.options,
    source_refs: rec.source_refs,
    channels,
    starred: rec.starred,
    created_at: rec.created_at,
    updated_at: rec.updated_at,
    expires_at: rec.expires_at,
  };
}
