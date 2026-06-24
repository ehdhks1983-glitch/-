// lib/store/supabase.ts — Supabase(Postgres) 백엔드. 주입된 클라이언트의 권한을 따른다.
//   요청 컨텍스트: user-session 클라이언트(RLS 본인 스코프) → create/getById/listByOwner
//   워커 컨텍스트:  service_role(admin) 클라이언트 → claimNext/update/addOutput
// 큐 점유는 claim_next_generation RPC(FOR UPDATE SKIP LOCKED)로 동시성 안전.

import type { SupabaseClient } from "@supabase/supabase-js";
import type { GenerationOutput } from "@/lib/multipublish/types";
import type {
  CreateGenerationInput,
  GenerationPatch,
  GenerationStore,
  OutputInput,
  StoredGeneration,
} from "./types";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Row = Record<string, any>;

function mapGeneration(g: Row, outputs: GenerationOutput[] = []): StoredGeneration {
  return {
    id: g.id,
    owner: g.owner,
    keyword: g.keyword ?? "",
    title: g.title ?? "",
    source_refs: Array.isArray(g.source_refs) ? g.source_refs : [],
    options: g.options ?? { tone: 50, monetize: false, channels: [] },
    core: g.core ?? null,
    status: g.status ?? "queued",
    error: g.error ?? null,
    starred: Boolean(g.starred),
    outputs,
    created_at: g.created_at,
    updated_at: g.updated_at,
    expires_at: g.expires_at ?? null,
  };
}

function mapOutput(o: Row): GenerationOutput {
  return {
    channel: o.channel,
    variant_no: o.variant_no,
    status: o.status ?? "done",
    content: o.content ?? {},
    ai_cost_usd: Number(o.ai_cost_usd ?? 0),
    error: o.error ?? undefined,
  };
}

export function createSupabaseStore(client: SupabaseClient): GenerationStore {
  return {
    async create(input: CreateGenerationInput): Promise<StoredGeneration> {
      const { data, error } = await client
        .from("generations")
        .insert({
          owner: input.owner,
          keyword: input.keyword,
          title: input.title ?? "",
          source_refs: input.sourceUrls.map((url) => ({ url, ok: false })),
          options: input.options,
          status: "queued",
          expires_at: input.expiresAt ?? null,
        })
        .select()
        .single();
      if (error) throw new Error(`generation 생성 실패: ${error.message}`);
      return mapGeneration(data);
    },

    async getById(id: string, owner?: string): Promise<StoredGeneration | null> {
      let q = client.from("generations").select("*").eq("id", id);
      if (owner) q = q.eq("owner", owner);
      const { data: g, error } = await q.maybeSingle();
      if (error) throw new Error(`generation 조회 실패: ${error.message}`);
      if (!g) return null;
      const { data: outs, error: oErr } = await client
        .from("generation_outputs")
        .select("*")
        .eq("generation_id", id)
        .order("variant_no", { ascending: true });
      if (oErr) throw new Error(`outputs 조회 실패: ${oErr.message}`);
      return mapGeneration(g, (outs ?? []).map(mapOutput));
    },

    async listByOwner(owner: string, limit = 100): Promise<StoredGeneration[]> {
      const { data, error } = await client
        .from("generations")
        .select("*")
        .eq("owner", owner)
        .order("created_at", { ascending: false })
        .limit(limit);
      if (error) throw new Error(`목록 조회 실패: ${error.message}`);
      return (data ?? []).map((g) => mapGeneration(g));
    },

    async countActiveByOwner(owner: string): Promise<number> {
      const { count, error } = await client
        .from("generations")
        .select("*", { count: "exact", head: true })
        .eq("owner", owner)
        .in("status", ["queued", "processing"]);
      if (error) throw new Error(`진행중 카운트 실패: ${error.message}`);
      return count ?? 0;
    },

    async claimNext(): Promise<StoredGeneration | null> {
      const { data, error } = await client.rpc("claim_next_generation");
      if (error) throw new Error(`claim 실패: ${error.message}`);
      if (!data) return null;
      const row = Array.isArray(data) ? data[0] : data;
      return row ? mapGeneration(row) : null;
    },

    async update(id: string, patch: GenerationPatch): Promise<void> {
      const row: Row = {};
      if (patch.status !== undefined) row.status = patch.status;
      if (patch.core !== undefined) row.core = patch.core;
      if (patch.error !== undefined) row.error = patch.error;
      if (patch.title !== undefined) row.title = patch.title;
      if (patch.source_refs !== undefined) row.source_refs = patch.source_refs;
      if (patch.expires_at !== undefined) row.expires_at = patch.expires_at;
      if (Object.keys(row).length === 0) return;
      const { error } = await client.from("generations").update(row).eq("id", id);
      if (error) throw new Error(`generation 갱신 실패: ${error.message}`);
    },

    async addOutput(id: string, output: OutputInput): Promise<number> {
      // 채널별 max(variant_no)+1. 동시 재생성 충돌(unique index 23505) 시 재계산·재시도.
      for (let attempt = 0; attempt < 4; attempt++) {
        const { data: existing, error: qErr } = await client
          .from("generation_outputs")
          .select("variant_no")
          .eq("generation_id", id)
          .eq("channel", output.channel)
          .order("variant_no", { ascending: false })
          .limit(1);
        if (qErr) throw new Error(`variant 조회 실패: ${qErr.message}`);
        const variant_no = (existing?.[0]?.variant_no ?? 0) + 1;

        const { error } = await client.from("generation_outputs").insert({
          generation_id: id,
          channel: output.channel,
          variant_no,
          status: output.status,
          content: output.content,
          ai_cost_usd: output.ai_cost_usd,
        });
        if (!error) return variant_no;
        if (error.code === "23505") continue; // unique 충돌 → 재계산
        throw new Error(`output 저장 실패: ${error.message}`);
      }
      throw new Error("output 저장 실패: variant 충돌 재시도 초과");
    },
  };
}
