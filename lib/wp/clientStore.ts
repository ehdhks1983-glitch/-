// lib/wp/clientStore.ts  [신규 — 워드프레스 자동 발행] ※ 브라우저 전용
// 접속 정보는 이 브라우저의 localStorage 에만 저장한다(서버 무저장 — README 보안 절).
// localStorage 는 "외부 스토어"이므로 훅은 useSyncExternalStore 로 구독한다(React 권장 패턴).
// wpApi(): 저장된 접속 정보를 헤더에 실어 /api/wp/* 를 호출하는 공용 fetch 래퍼.

import { useSyncExternalStore } from "react";
import { encodeWpConnection, WP_CONNECTION_HEADER } from "./connection";
import type { WpConnection } from "./types";

const STORAGE_KEY = "promptsite:wp:connection";
/** 같은 탭 안에서의 저장/해제 알림(storage 이벤트는 다른 탭에만 오므로 별도 이벤트) */
const CHANGE_EVENT = "promptsite:wp:connection-change";

/** 저장본에는 화면 표시용 메타(사이트 이름 등)를 함께 담는다. */
export interface SavedWpConnection extends WpConnection {
  siteName: string;
  userName: string;
  savedAt: string;
}

function parseSaved(raw: string): SavedWpConnection | null {
  try {
    const c = JSON.parse(raw) as Partial<SavedWpConnection>;
    if (
      typeof c.url !== "string" ||
      typeof c.user !== "string" ||
      typeof c.appPassword !== "string" ||
      !c.url ||
      !c.user ||
      !c.appPassword
    ) {
      return null;
    }
    return {
      url: c.url,
      user: c.user,
      appPassword: c.appPassword,
      siteName: typeof c.siteName === "string" ? c.siteName : c.url,
      userName: typeof c.userName === "string" ? c.userName : c.user,
      savedAt: typeof c.savedAt === "string" ? c.savedAt : "",
    };
  } catch {
    return null;
  }
}

// useSyncExternalStore 는 스냅샷 참조가 안정적이어야 한다(매 호출 새 객체 금지)
// → 원본 문자열이 바뀔 때만 다시 파싱해 캐시한다.
let snapshotRaw: string | null = null;
let snapshotConn: SavedWpConnection | null = null;

export function loadWpConnection(): SavedWpConnection | null {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    raw = null; // 접근 불가 환경(시크릿 모드 등)
  }
  if (raw !== snapshotRaw) {
    snapshotRaw = raw;
    snapshotConn = raw ? parseSaved(raw) : null;
  }
  return snapshotConn;
}

function emitConnectionChange(): void {
  try {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  } catch {
    // 무시
  }
}

export function saveWpConnection(conn: SavedWpConnection): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conn));
  } catch {
    // 저장 불가 환경은 세션 내 상태로만 동작
  }
  emitConnectionChange();
}

export function clearWpConnection(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 무시
  }
  emitConnectionChange();
}

function subscribeConnection(cb: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, cb);
  window.addEventListener("storage", cb); // 다른 탭에서의 변경
  return () => {
    window.removeEventListener(CHANGE_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

const SERVER_SNAPSHOT = undefined;

/**
 * 저장된 접속 정보 훅. save/clear 호출 시 자동으로 최신값으로 갱신된다.
 * undefined = 확인 중(SSR/하이드레이션), null = 미연결, 객체 = 연결됨.
 */
export function useWpConnection(): SavedWpConnection | null | undefined {
  return useSyncExternalStore(
    subscribeConnection,
    loadWpConnection,
    () => SERVER_SNAPSHOT,
  );
}

/** wpApi 실패 — HTTP 상태를 함께 담아 호출부가 429(속도 제한) 재시도 등을 판단할 수 있게 한다. */
export class WpApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/**
 * /api/wp/* 호출 래퍼. 저장된 접속 정보를 x-wp-connection 헤더로 동봉.
 * 실패 시 서버가 준 한국어 안내 메시지를 WpApiClientError 로 던진다.
 */
export async function wpApi<T>(
  path: string,
  init: { method?: string; json?: unknown } = {},
): Promise<T> {
  const conn = loadWpConnection();
  if (!conn) {
    throw new WpApiClientError("워드프레스 연결이 필요해요. [연결 설정]에서 먼저 연결해 주세요.", 401);
  }

  const res = await fetch(path, {
    method: init.method ?? (init.json !== undefined ? "POST" : "GET"),
    headers: {
      [WP_CONNECTION_HEADER]: encodeWpConnection(conn),
      ...(init.json !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init.json !== undefined ? JSON.stringify(init.json) : undefined,
  });

  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new WpApiClientError(
      data?.error || "요청에 실패했어요. 잠시 후 다시 시도해 주세요.",
      res.status,
    );
  }
  return data;
}

/** WP의 GMT 시각("YYYY-MM-DDTHH:mm:ss") → 사용자 로컬 표기 */
export function formatWpDate(dateGmt: string): string {
  if (!dateGmt) return "-";
  const iso = /Z|[+-]\d{2}:\d{2}$/.test(dateGmt) ? dateGmt : `${dateGmt}Z`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return dateGmt;
  return d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}
