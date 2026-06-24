// lib/store/types.ts — 생성 잡 저장소 추상화.
// generations.status 를 큐로 사용(queued→processing→done/partial/failed) — 별도 jobs 테이블 없음(스펙 §3 "MVP 단순").
// 두 백엔드: Supabase(운영) / 인메모리(키리스 개발·검증). 워커/요청 컨텍스트가 동일 인터페이스 사용.

import type {
  Channel,
  Core,
  GenOptions,
  GenerationOutput,
  GenerationStatus,
  SourceRef,
} from "@/lib/multipublish/types";

export interface CreateGenerationInput {
  owner: string;
  keyword: string;
  title?: string;
  sourceUrls: string[];
  options: GenOptions;
  expiresAt?: string | null;
}

export interface StoredGeneration {
  id: string;
  owner: string;
  keyword: string;
  title: string;
  source_refs: SourceRef[];
  options: GenOptions;
  core: Core | null;
  status: GenerationStatus;
  error: string | null;
  starred: boolean;
  outputs: GenerationOutput[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface GenerationPatch {
  status?: GenerationStatus;
  core?: Core | null;
  error?: string | null;
  title?: string;
  source_refs?: SourceRef[];
  expires_at?: string | null;
}

/** addOutput 입력(변형 번호는 저장소가 채널별로 자동 증가). */
export type OutputInput = Omit<GenerationOutput, "variant_no">;

export interface GenerationStore {
  /** 잡 생성(status=queued). */
  create(input: CreateGenerationInput): Promise<StoredGeneration>;
  /** 단건 조회. owner 지정 시 소유자 스코프. */
  getById(id: string, owner?: string): Promise<StoredGeneration | null>;
  /** 소유자 발행물 목록(최신순). */
  listByOwner(owner: string, limit?: number): Promise<StoredGeneration[]>;
  /** 진행 중(queued/processing) 잡 개수 — 동시 생성 과금 가드용(TOCTOU 완화). */
  countActiveByOwner(owner: string): Promise<number>;
  /** 큐에서 다음 잡 원자적 점유(queued→processing). 없으면 null. */
  claimNext(): Promise<StoredGeneration | null>;
  /** 잡 필드 갱신. */
  update(id: string, patch: GenerationPatch): Promise<void>;
  /** 채널 산출물 추가. 채널별 variant_no 자동 증가. 부여된 variant_no 반환. */
  addOutput(id: string, output: OutputInput): Promise<number>;
}

/** 채널별 최신 variant 산출물만 추림(UI/조회용). */
export function latestOutputs(outputs: GenerationOutput[]): GenerationOutput[] {
  const byChannel = new Map<Channel, GenerationOutput>();
  for (const o of outputs) {
    const cur = byChannel.get(o.channel);
    if (!cur || o.variant_no > cur.variant_no) byChannel.set(o.channel, o);
  }
  return [...byChannel.values()];
}
