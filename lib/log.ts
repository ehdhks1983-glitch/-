// lib/log.ts — 구조화 로깅 (스펙 §13: INFO/WARN/ERROR 레벨, 핵심 단계 로그).
// 워커/스크래퍼/파이프라인/과금 공용. 콘솔 기반(운영에선 수집기로 교체 가능).

type Level = "INFO" | "WARN" | "ERROR";

function emit(level: Level, scope: string, msg: string, meta?: Record<string, unknown>) {
  const head = `${new Date().toISOString()} [${level}] ${scope}: ${msg}`;
  const line = meta && Object.keys(meta).length ? `${head} ${safe(meta)}` : head;
  if (level === "ERROR") console.error(line);
  else if (level === "WARN") console.warn(line);
  else console.log(line);
}

function safe(meta: Record<string, unknown>): string {
  try {
    return JSON.stringify(meta);
  } catch {
    return "[unserializable meta]";
  }
}

export interface Logger {
  info: (msg: string, meta?: Record<string, unknown>) => void;
  warn: (msg: string, meta?: Record<string, unknown>) => void;
  error: (msg: string, meta?: Record<string, unknown>) => void;
}

export function createLogger(scope: string): Logger {
  return {
    info: (m, meta) => emit("INFO", scope, m, meta),
    warn: (m, meta) => emit("WARN", scope, m, meta),
    error: (m, meta) => emit("ERROR", scope, m, meta),
  };
}
