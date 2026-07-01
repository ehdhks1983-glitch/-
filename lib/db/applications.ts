// lib/db/applications.ts  — 서버 전용 신청(applications) 쿼리 헬퍼.

import type { SupabaseClient } from "@supabase/supabase-js";
import type { ApplicationKind } from "@/lib/applications";

export interface ApplicationRow {
  id: string;
  kind: ApplicationKind;
  name: string;
  email: string;
  phone: string | null;
  region: string | null;
  payload: Record<string, unknown>;
  status: "new" | "reviewing" | "accepted" | "rejected";
  created_at: string;
}

export interface NewApplication {
  kind: ApplicationKind;
  name: string;
  email: string;
  phone?: string;
  region?: string;
  payload: Record<string, unknown>;
}

/** 공개 신청 폼 저장. RLS 정책상 kind 가 host/creator 일 때만 insert 허용. */
export async function insertApplication(supabase: SupabaseClient, app: NewApplication): Promise<void> {
  const { error } = await supabase.from("applications").insert({
    kind: app.kind,
    name: app.name,
    email: app.email.toLowerCase(),
    phone: app.phone ?? null,
    region: app.region ?? null,
    payload: app.payload,
  });
  if (error) throw new Error(error.message);
}

/** 관리자(service_role) 전용 신청 목록. 최신순. kind 로 필터 가능. */
export async function listApplications(
  admin: SupabaseClient,
  kind?: ApplicationKind,
): Promise<ApplicationRow[]> {
  let query = admin.from("applications").select("*").order("created_at", { ascending: false }).limit(500);
  if (kind) query = query.eq("kind", kind);
  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return (data ?? []) as ApplicationRow[];
}
