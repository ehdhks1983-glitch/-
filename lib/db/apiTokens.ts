// lib/db/apiTokens.ts  [신규 — P2 MCP 연동] — 개인 액세스 토큰(서버 전용).
// 원문 토큰은 발급 응답으로 한 번만 돌려주고, DB 에는 SHA-256 해시와 앞 몇 글자(표시용)만 남긴다.

import { createHash, randomBytes } from "node:crypto";
import type { SupabaseClient } from "@supabase/supabase-js";

export interface ApiTokenRow {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

const TOKEN_PREFIX = "ps_";

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

/** 새 토큰 발급(로그인 세션 클라이언트 — RLS 로 본인 행만 생성). 원문은 이 반환값에만 있다. */
export async function issueToken(
  supabase: SupabaseClient,
  owner: string,
  name: string,
): Promise<{ token: string; row: ApiTokenRow }> {
  const token = TOKEN_PREFIX + randomBytes(24).toString("base64url");
  const { data, error } = await supabase
    .from("api_tokens")
    .insert({ owner, name: name.slice(0, 60), token_hash: hashToken(token), prefix: token.slice(0, 8) })
    .select("id, name, prefix, created_at, last_used_at, revoked_at")
    .single();
  if (error) throw new Error(error.message);
  return { token, row: data as ApiTokenRow };
}

export async function selectMyTokens(supabase: SupabaseClient, owner: string): Promise<ApiTokenRow[]> {
  const { data, error } = await supabase
    .from("api_tokens")
    .select("id, name, prefix, created_at, last_used_at, revoked_at")
    .eq("owner", owner)
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as ApiTokenRow[];
}

export async function revokeToken(supabase: SupabaseClient, id: string, owner: string): Promise<boolean> {
  const { data, error } = await supabase
    .from("api_tokens")
    .update({ revoked_at: new Date().toISOString() })
    .eq("id", id)
    .eq("owner", owner)
    .is("revoked_at", null)
    .select("id");
  if (error) throw new Error(error.message);
  return (data ?? []).length > 0;
}

/** Bearer 토큰 → 소유자 id. 관리자(service_role) 클라이언트 전용. 폐기됐거나 없으면 null. */
export async function resolveToken(admin: SupabaseClient, token: string): Promise<string | null> {
  if (!token.startsWith(TOKEN_PREFIX)) return null;
  const { data, error } = await admin
    .from("api_tokens")
    .select("id, owner")
    .eq("token_hash", hashToken(token))
    .is("revoked_at", null)
    .maybeSingle();
  if (error || !data) return null;
  // 마지막 사용 시각은 실패해도 무시(인증 결과에 영향 없음)
  void admin.from("api_tokens").update({ last_used_at: new Date().toISOString() }).eq("id", data.id).then(() => {});
  return data.owner as string;
}
