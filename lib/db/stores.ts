// lib/db/stores.ts  [신규 — P2 여러 매장] — 매장(프로젝트 묶음) 쿼리(서버 전용, RLS 소유자).

import type { SupabaseClient } from "@supabase/supabase-js";

export interface StoreRow {
  id: string;
  name: string;
  created_at: string;
}

export async function selectMyStores(supabase: SupabaseClient, owner: string): Promise<StoreRow[]> {
  const { data, error } = await supabase
    .from("stores")
    .select("id, name, created_at")
    .eq("owner", owner)
    .order("created_at", { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []) as StoreRow[];
}

export async function insertStore(supabase: SupabaseClient, owner: string, name: string): Promise<StoreRow> {
  const { data, error } = await supabase
    .from("stores")
    .insert({ owner, name: name.slice(0, 40) })
    .select("id, name, created_at")
    .single();
  if (error) throw new Error(error.message);
  return data as StoreRow;
}

/** 매장 삭제. 소속 페이지는 지우지 않고 '매장 미지정'으로 남는다(FK on delete set null). */
export async function deleteStore(supabase: SupabaseClient, id: string, owner: string): Promise<void> {
  const { error } = await supabase.from("stores").delete().eq("id", id).eq("owner", owner);
  if (error) throw new Error(error.message);
}

export async function isMyStore(supabase: SupabaseClient, id: string, owner: string): Promise<boolean> {
  const { data } = await supabase.from("stores").select("id").eq("id", id).eq("owner", owner).maybeSingle();
  return Boolean(data);
}
