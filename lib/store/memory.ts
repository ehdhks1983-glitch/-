// lib/store/memory.ts — 인메모리 생성 저장소(키리스 개발/검증). 단일 프로세스 가정.
// Supabase 미설정 시 요청/워커가 동일 싱글톤을 공유한다(in-process kick 으로 워커 tick).

import type {
  CreateGenerationInput,
  GenerationPatch,
  GenerationStore,
  OutputInput,
  StoredGeneration,
} from "./types";

const DB = new Map<string, StoredGeneration>();

function nowIso(): string {
  return new Date().toISOString();
}

function clone<T>(v: T): T {
  return structuredClone(v);
}

export const memoryStore: GenerationStore = {
  async create(input: CreateGenerationInput): Promise<StoredGeneration> {
    const id = crypto.randomUUID();
    const ts = nowIso();
    const rec: StoredGeneration = {
      id,
      owner: input.owner,
      keyword: input.keyword,
      title: input.title ?? "",
      source_refs: input.sourceUrls.map((url) => ({ url, ok: false })),
      options: input.options,
      core: null,
      status: "queued",
      error: null,
      starred: false,
      outputs: [],
      created_at: ts,
      updated_at: ts,
      expires_at: input.expiresAt ?? null,
    };
    DB.set(id, rec);
    return clone(rec);
  },

  async getById(id: string, owner?: string): Promise<StoredGeneration | null> {
    const rec = DB.get(id);
    if (!rec) return null;
    if (owner && rec.owner !== owner) return null;
    return clone(rec);
  },

  async listByOwner(owner: string, limit = 100): Promise<StoredGeneration[]> {
    return [...DB.values()]
      .filter((r) => r.owner === owner)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
      .slice(0, limit)
      .map(clone);
  },

  async claimNext(): Promise<StoredGeneration | null> {
    // 가장 오래된 queued 1건 → processing (단일 프로세스라 원자성 보장).
    const queued = [...DB.values()]
      .filter((r) => r.status === "queued")
      .sort((a, b) => (a.created_at < b.created_at ? -1 : 1));
    const next = queued[0];
    if (!next) return null;
    next.status = "processing";
    next.updated_at = nowIso();
    return clone(next);
  },

  async update(id: string, patch: GenerationPatch): Promise<void> {
    const rec = DB.get(id);
    if (!rec) return;
    if (patch.status !== undefined) rec.status = patch.status;
    if (patch.core !== undefined) rec.core = patch.core;
    if (patch.error !== undefined) rec.error = patch.error;
    if (patch.title !== undefined) rec.title = patch.title;
    if (patch.source_refs !== undefined) rec.source_refs = patch.source_refs;
    if (patch.expires_at !== undefined) rec.expires_at = patch.expires_at;
    rec.updated_at = nowIso();
  },

  async addOutput(id: string, output: OutputInput): Promise<number> {
    const rec = DB.get(id);
    if (!rec) throw new Error(`generation 없음: ${id}`);
    const maxForChannel = rec.outputs
      .filter((o) => o.channel === output.channel)
      .reduce((m, o) => Math.max(m, o.variant_no), 0);
    const variant_no = maxForChannel + 1;
    rec.outputs.push({ ...output, variant_no } as StoredGeneration["outputs"][number]);
    rec.updated_at = nowIso();
    return variant_no;
  },
};

/** 검증/디버그용: 전체 비우기. */
export function __resetMemoryStore() {
  DB.clear();
}
