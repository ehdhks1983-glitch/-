// lib/store/index.ts — 컨텍스트별 저장소 팩토리.
//   requestStore(): 요청(API/UI) — 키리스=메모리, Supabase=user-session(RLS 본인 스코프)
//   workerStore():  워커        — 키리스=메모리, Supabase=service_role(admin, RLS 우회)
// 둘 다 같은 데이터(메모리 싱글톤 또는 같은 테이블)를 본다. 차이는 권한뿐.

import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseAdmin, createSupabaseServer } from "@/lib/db/supabase-server";
import { memoryStore } from "./memory";
import { createSupabaseStore } from "./supabase";
import type { GenerationStore } from "./types";

export async function requestStore(): Promise<GenerationStore> {
  if (!isSupabaseConfigured()) return memoryStore;
  const client = await createSupabaseServer();
  return createSupabaseStore(client);
}

export function workerStore(): GenerationStore {
  if (!isSupabaseConfigured()) return memoryStore;
  const admin = createSupabaseAdmin();
  if (!admin) throw new Error("워커 저장소: SUPABASE_SERVICE_ROLE_KEY 가 필요합니다.");
  return createSupabaseStore(admin);
}

export * from "./types";
