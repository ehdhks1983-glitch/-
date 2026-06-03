import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import type { LicenseStatus, PlanType } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const KST = "Asia/Seoul";

export function formatDateTimeKST(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: KST,
  }).format(new Date(iso));
}

export function formatDateKST(iso: string | null | undefined, fallback = "무제한"): string {
  if (!iso) return fallback;
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeZone: KST,
  }).format(new Date(iso));
}

export const PLAN_LABELS: Record<PlanType, string> = {
  trial_7: "7일 체험",
  monthly_30: "30일",
  unlimited: "무제한",
  custom: "커스텀",
};

export const STATUS_LABELS: Record<LicenseStatus, string> = {
  active: "활성",
  revoked: "취소됨",
  expired: "만료",
};

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}
