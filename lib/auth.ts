// lib/auth.ts — 현재 사용자(owner) 식별. API 라우트 공용.
//   Supabase 설정: 세션 사용자 id(없으면 null → 401)
//   키리스(미설정): 고정 dev owner(개발/검증용 단일 사용자)

import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";

/** 키리스 모드의 고정 소유자 id. */
export const DEV_OWNER = "dev-user";

export interface OwnerInfo {
  owner: string | null;
  configured: boolean;
}

export async function currentOwner(): Promise<OwnerInfo> {
  if (!isSupabaseConfigured()) return { owner: DEV_OWNER, configured: false };
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return { owner: user?.id ?? null, configured: true };
}
