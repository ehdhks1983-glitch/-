// lib/license/db.ts  [신규] — 라이선스 DB 헬퍼(서버 전용).
// 전부 service_role(admin) 클라이언트를 받아 동작한다. 라이선스 테이블은 RLS 잠금이라
// anon/로그인 세션으로는 접근 불가 → 호출자가 createSupabaseAdmin()을 넘겨야 한다.

import type { SupabaseClient } from "@supabase/supabase-js";
import { bots, VERIFY_REASONS, type VerifyReason } from "./config";
import { generateCode, normalizeCode } from "./codes";

export type LicenseStatus = "active" | "revoked";

export interface LicenseRow {
  id: string;
  code: string;
  label: string;
  status: LicenseStatus;
  max_devices: number;
  expires_at: string | null;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface ActivationRow {
  id: string;
  license_id: string;
  device_id: string;
  device_label: string;
  last_bot_id: string;
  first_seen_at: string;
  last_seen_at: string;
}

/** 목록 + 각 라이선스의 활성 기기 수(관리 화면용). */
export interface LicenseWithUsage extends LicenseRow {
  devices_used: number;
  last_seen_at: string | null;
}

export interface NewLicenseInput {
  label?: string;
  note?: string;
  maxDevices?: number;
  /** 유효기간(일). 0/미지정이면 무기한. expiresAt 가 우선. */
  validDays?: number | null;
  expiresAt?: string | null;
}

// ───────────────────────── 관리: 발급/조회/상태변경 ─────────────────────────

export async function listLicenses(admin: SupabaseClient): Promise<LicenseWithUsage[]> {
  const { data: licenses, error } = await admin
    .from("licenses")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  const rows = (licenses ?? []) as LicenseRow[];
  if (rows.length === 0) return [];

  const ids = rows.map((r) => r.id);
  const { data: acts, error: aErr } = await admin
    .from("license_activations")
    .select("license_id,last_seen_at")
    .in("license_id", ids);
  if (aErr) throw new Error(aErr.message);

  const used = new Map<string, number>();
  const last = new Map<string, string>();
  for (const a of (acts ?? []) as Pick<ActivationRow, "license_id" | "last_seen_at">[]) {
    used.set(a.license_id, (used.get(a.license_id) ?? 0) + 1);
    const prev = last.get(a.license_id);
    if (!prev || a.last_seen_at > prev) last.set(a.license_id, a.last_seen_at);
  }
  return rows.map((r) => ({
    ...r,
    devices_used: used.get(r.id) ?? 0,
    last_seen_at: last.get(r.id) ?? null,
  }));
}

function resolveExpiry(input: NewLicenseInput): string | null {
  if (input.expiresAt) return input.expiresAt;
  if (input.validDays && input.validDays > 0) {
    const ms = input.validDays * 24 * 60 * 60 * 1000;
    return new Date(Date.now() + ms).toISOString();
  }
  return null;
}

/** 새 코드 발급. 코드 충돌 시 몇 번 재시도. */
export async function createLicense(admin: SupabaseClient, input: NewLicenseInput): Promise<LicenseRow> {
  const maxDevices = Math.max(1, Math.min(999, Math.floor(input.maxDevices ?? 1)));
  const expires_at = resolveExpiry(input);
  const label = (input.label ?? "").trim().slice(0, 120);
  const note = (input.note ?? "").trim().slice(0, 500);

  let lastErr: unknown = null;
  for (let attempt = 0; attempt < 5; attempt++) {
    const code = generateCode();
    const { data, error } = await admin
      .from("licenses")
      .insert({ code, label, note, max_devices: maxDevices, expires_at, status: "active" })
      .select()
      .single();
    if (!error) return data as LicenseRow;
    // 23505 = unique 위반(코드 충돌) → 재시도. 그 외엔 즉시 실패.
    if (!String(error.code).includes("23505")) throw new Error(error.message);
    lastErr = error;
  }
  throw new Error(`코드 생성에 반복 실패했습니다: ${String(lastErr)}`);
}

export async function setLicenseStatus(
  admin: SupabaseClient,
  id: string,
  status: LicenseStatus,
): Promise<LicenseRow | null> {
  const { data, error } = await admin
    .from("licenses")
    .update({ status, updated_at: new Date().toISOString() })
    .eq("id", id)
    .select()
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as LicenseRow) ?? null;
}

export interface LicensePatch {
  label?: string;
  note?: string;
  maxDevices?: number;
  expiresAt?: string | null;
}

export async function updateLicense(
  admin: SupabaseClient,
  id: string,
  patch: LicensePatch,
): Promise<LicenseRow | null> {
  const fields: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (typeof patch.label === "string") fields.label = patch.label.trim().slice(0, 120);
  if (typeof patch.note === "string") fields.note = patch.note.trim().slice(0, 500);
  if (typeof patch.maxDevices === "number") {
    fields.max_devices = Math.max(1, Math.min(999, Math.floor(patch.maxDevices)));
  }
  if (patch.expiresAt !== undefined) fields.expires_at = patch.expiresAt;

  const { data, error } = await admin
    .from("licenses")
    .update(fields)
    .eq("id", id)
    .select()
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as LicenseRow) ?? null;
}

export async function deleteLicense(admin: SupabaseClient, id: string): Promise<void> {
  // activations/checks 는 FK on delete cascade 로 함께 정리된다.
  const { error } = await admin.from("licenses").delete().eq("id", id);
  if (error) throw new Error(error.message);
}

/** 기기 바인딩 초기화(고객 PC 교체 시). 활성 기기 전부 해제. */
export async function resetDevices(admin: SupabaseClient, id: string): Promise<number> {
  const { data, error } = await admin
    .from("license_activations")
    .delete()
    .eq("license_id", id)
    .select("id");
  if (error) throw new Error(error.message);
  return (data ?? []).length;
}

// ───────────────────────── 봇 검증(공개 API 코어) ─────────────────────────

export interface VerifyInput {
  code: string;
  deviceId: string;
  botId?: string;
  deviceLabel?: string;
}

export interface VerifyResult {
  valid: boolean;
  reason: VerifyReason;
  message: string;
  license?: {
    label: string;
    status: LicenseStatus;
    expires_at: string | null;
    bots: string[];
    devices: { used: number; max: number };
  };
}

const REASON_MESSAGE: Record<VerifyReason, string> = {
  ok: "인증되었습니다.",
  not_found: "존재하지 않는 코드입니다.",
  revoked: "정지된 코드입니다.",
  inactive: "사용할 수 없는 코드입니다.",
  expired: "만료된 코드입니다.",
  device_limit: "허용 기기 수를 초과했습니다.",
};

function result(reason: VerifyReason, license?: VerifyResult["license"]): VerifyResult {
  return { valid: reason === VERIFY_REASONS.ok, reason, message: REASON_MESSAGE[reason], license };
}

/**
 * 봇이 호출하는 온라인 검증의 핵심 로직.
 * 통과 시 (필요하면) 기기를 바인딩하고 last_seen 을 갱신한다. 검증 호출은 항상 로그에 남긴다.
 */
export async function verifyLicense(admin: SupabaseClient, input: VerifyInput): Promise<VerifyResult> {
  const normalized = normalizeCode(input.code);
  const deviceId = (input.deviceId ?? "").trim().slice(0, 200);
  const botId = (input.botId ?? "").trim().slice(0, 60);
  const deviceLabel = (input.deviceLabel ?? "").trim().slice(0, 120);

  if (!normalized) {
    await logCheck(admin, null, deviceId, botId, VERIFY_REASONS.notFound);
    return result(VERIFY_REASONS.notFound);
  }

  const { data: lic, error } = await admin
    .from("licenses")
    .select("*")
    .eq("code", normalized)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!lic) {
    await logCheck(admin, null, deviceId, botId, VERIFY_REASONS.notFound);
    return result(VERIFY_REASONS.notFound);
  }
  const license = lic as LicenseRow;

  if (license.status === "revoked") {
    await logCheck(admin, license.id, deviceId, botId, VERIFY_REASONS.revoked);
    return result(VERIFY_REASONS.revoked);
  }
  if (license.status !== "active") {
    await logCheck(admin, license.id, deviceId, botId, VERIFY_REASONS.inactive);
    return result(VERIFY_REASONS.inactive);
  }
  if (license.expires_at && new Date(license.expires_at).getTime() <= Date.now()) {
    await logCheck(admin, license.id, deviceId, botId, VERIFY_REASONS.expired);
    return result(VERIFY_REASONS.expired);
  }

  // 기기 바인딩 처리.
  const nowIso = new Date().toISOString();
  let devicesUsed = 0;

  if (deviceId) {
    const { data: existing, error: exErr } = await admin
      .from("license_activations")
      .select("id")
      .eq("license_id", license.id)
      .eq("device_id", deviceId)
      .maybeSingle();
    if (exErr) throw new Error(exErr.message);

    if (existing) {
      await admin
        .from("license_activations")
        .update({ last_seen_at: nowIso, last_bot_id: botId, device_label: deviceLabel })
        .eq("id", (existing as { id: string }).id);
    } else {
      const { count, error: cErr } = await admin
        .from("license_activations")
        .select("id", { count: "exact", head: true })
        .eq("license_id", license.id);
      if (cErr) throw new Error(cErr.message);
      if ((count ?? 0) >= license.max_devices) {
        await logCheck(admin, license.id, deviceId, botId, VERIFY_REASONS.deviceLimit);
        return result(VERIFY_REASONS.deviceLimit, usageLicense(license, count ?? 0));
      }
      const { error: insErr } = await admin.from("license_activations").insert({
        license_id: license.id,
        device_id: deviceId,
        device_label: deviceLabel,
        last_bot_id: botId,
        first_seen_at: nowIso,
        last_seen_at: nowIso,
      });
      // 동시 호출로 unique 위반이 나도 "이미 바인딩된 기기"이므로 통과 처리.
      if (insErr && !String(insErr.code).includes("23505")) throw new Error(insErr.message);
    }
  }

  const { count: finalCount } = await admin
    .from("license_activations")
    .select("id", { count: "exact", head: true })
    .eq("license_id", license.id);
  devicesUsed = finalCount ?? 0;

  await logCheck(admin, license.id, deviceId, botId, VERIFY_REASONS.ok);
  return result(VERIFY_REASONS.ok, usageLicense(license, devicesUsed));
}

function usageLicense(license: LicenseRow, used: number): VerifyResult["license"] {
  return {
    label: license.label,
    status: license.status,
    expires_at: license.expires_at,
    bots: bots().map((b) => b.id),
    devices: { used, max: license.max_devices },
  };
}

/** 검증 호출 로그(베스트 에포트 — 실패해도 검증 결과엔 영향 없음). */
async function logCheck(
  admin: SupabaseClient,
  licenseId: string | null,
  deviceId: string,
  botId: string,
  reason: VerifyReason,
): Promise<void> {
  try {
    await admin.from("license_checks").insert({
      license_id: licenseId,
      device_id: deviceId || null,
      bot_id: botId || null,
      reason,
    });
  } catch {
    // 로그 실패는 무시.
  }
}
