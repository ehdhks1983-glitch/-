// lib/threads/validate.ts  [신규] — Threads 게시물 입력 검증(라우트 공통).

import { THREADS_MAX_TEXT } from "./config";
import type { ThreadsMediaType } from "./db";

export function cleanText(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

export function isValidText(text: string): boolean {
  return text.length > 0 && text.length <= THREADS_MAX_TEXT;
}

export function parseMediaType(v: unknown): ThreadsMediaType {
  return v === "IMAGE" ? "IMAGE" : "TEXT";
}

/** http(s) URL 이면 정규화해 반환, 아니면 null. */
export function parseImageUrl(v: unknown): string | null {
  if (typeof v !== "string" || !v.trim()) return null;
  try {
    const u = new URL(v.trim());
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

/** 미래 시각이면 ISO 문자열로 정규화해 반환, 아니면 null. */
export function parseFutureISO(v: unknown): string | null {
  if (typeof v !== "string" || !v.trim()) return null;
  const t = Date.parse(v);
  if (!Number.isFinite(t) || t <= Date.now()) return null;
  return new Date(t).toISOString();
}
