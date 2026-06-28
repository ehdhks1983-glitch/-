// lib/license/admin.ts  [신규] — 관리자 게이트(서버 전용).
// 라이선스 관리 화면/API 는 (1) 로그인 + (2) 관리자 이메일 허용목록 통과 + (3) service_role 키 보유
// 세 조건을 모두 만족해야 동작한다. 하나라도 빠지면 관리 기능은 비활성(차단)된다.

import type { SupabaseClient } from "@supabase/supabase-js";
import { createSupabaseAdmin, createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";

/** 허용 관리자 이메일 목록(env LICENSE_ADMIN_EMAILS, 쉼표 구분). 소문자 정규화. */
export function adminEmails(): string[] {
  return (process.env.LICENSE_ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

/** 라이선스 관리 기능을 켤 수 있는 환경인지(서비스키 + 관리자 1명 이상 + Supabase 설정). */
export function isLicenseAdminConfigured(): boolean {
  return isSupabaseConfigured() && Boolean(createSupabaseAdmin()) && adminEmails().length > 0;
}

export function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  return adminEmails().includes(email.toLowerCase());
}

export type AdminGate =
  | { ok: true; admin: SupabaseClient; userEmail: string }
  | { ok: false; status: 401 | 403 | 503; error: string };

/**
 * 라우트/페이지에서 공용으로 쓰는 관리자 인증 게이트.
 * 성공 시 service_role 클라이언트(admin)를 돌려준다(RLS 우회 — 라이선스 테이블 접근용).
 */
export async function requireAdmin(): Promise<AdminGate> {
  if (!isSupabaseConfigured()) {
    return { ok: false, status: 503, error: "Supabase가 설정되지 않았습니다." };
  }
  const admin = createSupabaseAdmin();
  if (!admin) {
    return { ok: false, status: 503, error: "SUPABASE_SERVICE_ROLE_KEY가 필요합니다." };
  }
  if (adminEmails().length === 0) {
    return { ok: false, status: 503, error: "LICENSE_ADMIN_EMAILS가 설정되지 않았습니다." };
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, status: 401, error: "로그인이 필요합니다." };
  if (!isAdminEmail(user.email)) {
    return { ok: false, status: 403, error: "관리자 권한이 없습니다." };
  }
  return { ok: true, admin, userEmail: user.email! };
}
