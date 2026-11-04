// lib/wp/clientStore.ts  [업데이트 — 워드프레스 자동 발행 v2] ※ 브라우저 전용
// 접속 정보는 이 브라우저의 localStorage 에만 저장한다(서버 무저장 — README 보안 절).
// v2: 여러 사이트를 저장하고 하나를 '사용 중'으로 고른다(대행·다중 블로그 운영).
//     v1 단일 저장본은 첫 로드 때 자동으로 옮겨온다.
// localStorage 는 "외부 스토어"이므로 훅은 useSyncExternalStore 로 구독한다(React 권장 패턴).
// wpApi()/wpUpload(): 사용 중인 접속 정보를 헤더에 실어 /api/wp/* 를 호출하는 공용 래퍼.

import { useSyncExternalStore } from "react";
import { encodeWpConnection, WP_CONNECTION_HEADER } from "./connection";
import type { SeoPlugin, WpConnection } from "./types";

const STORE_KEY = "promptsite:wp:connections";
const LEGACY_KEY = "promptsite:wp:connection";
/** 같은 탭 안에서의 저장/해제 알림(storage 이벤트는 다른 탭에만 오므로 별도 이벤트) */
const CHANGE_EVENT = "promptsite:wp:connection-change";

/** 저장본에는 화면 표시용 메타(사이트 이름·플러그인·타임존)를 함께 담는다. */
export interface SavedWpConnection extends WpConnection {
  /** url|user 로 만든 식별자 */
  id: string;
  siteName: string;
  userName: string;
  savedAt: string;
  seoPlugin: SeoPlugin;
  timezone: string;
  gmtOffset: number;
}

export interface WpStore {
  activeId: string | null;
  items: SavedWpConnection[];
}

export function connectionId(url: string, user: string): string {
  return `${url.toLowerCase()}|${user.toLowerCase()}`;
}

function parseItem(raw: unknown): SavedWpConnection | null {
  if (!raw || typeof raw !== "object") return null;
  const c = raw as Partial<SavedWpConnection>;
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
  const seo = c.seoPlugin;
  return {
    id: typeof c.id === "string" && c.id ? c.id : connectionId(c.url, c.user),
    url: c.url,
    user: c.user,
    appPassword: c.appPassword,
    siteName: typeof c.siteName === "string" ? c.siteName : c.url,
    userName: typeof c.userName === "string" ? c.userName : c.user,
    savedAt: typeof c.savedAt === "string" ? c.savedAt : "",
    seoPlugin: seo === "yoast" || seo === "rankmath" || seo === "aioseo" ? seo : null,
    timezone: typeof c.timezone === "string" ? c.timezone : "",
    gmtOffset: typeof c.gmtOffset === "number" ? c.gmtOffset : 0,
  };
}

function parseStore(raw: string | null): WpStore {
  if (!raw) return { activeId: null, items: [] };
  try {
    const s = JSON.parse(raw) as Partial<WpStore>;
    const items = Array.isArray(s.items)
      ? s.items.map(parseItem).filter((x): x is SavedWpConnection => x !== null)
      : [];
    const activeId =
      typeof s.activeId === "string" && items.some((i) => i.id === s.activeId)
        ? s.activeId
        : (items[0]?.id ?? null);
    return { activeId, items };
  } catch {
    return { activeId: null, items: [] };
  }
}

function writeStore(store: WpStore): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    // 저장 불가 환경(시크릿 모드 등)은 세션 내 상태로만 동작
  }
  emitConnectionChange();
}

/** v1 단일 저장본 → v2 목록으로 1회 이전 */
function migrateLegacy(): void {
  try {
    if (localStorage.getItem(STORE_KEY) !== null) return;
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (!legacy) return;
    const item = parseItem(JSON.parse(legacy));
    if (item) {
      localStorage.setItem(STORE_KEY, JSON.stringify({ activeId: item.id, items: [item] }));
    }
    localStorage.removeItem(LEGACY_KEY);
  } catch {
    // 이전 실패는 무시(새로 연결하면 됨)
  }
}

// useSyncExternalStore 는 스냅샷 참조가 안정적이어야 한다(매 호출 새 객체 금지)
// → 원본 문자열이 바뀔 때만 다시 파싱해 캐시한다.
let snapshotRaw: string | null = null;
let snapshotStore: WpStore = { activeId: null, items: [] };
let migrated = false;

export function loadWpStore(): WpStore {
  if (!migrated) {
    migrated = true;
    migrateLegacy();
  }
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORE_KEY);
  } catch {
    raw = null; // 접근 불가 환경
  }
  if (raw !== snapshotRaw) {
    snapshotRaw = raw;
    snapshotStore = parseStore(raw);
  }
  return snapshotStore;
}

/** 사용 중인 접속 정보(없으면 null). 참조는 스토어가 바뀔 때만 바뀐다. */
export function loadWpConnection(): SavedWpConnection | null {
  const s = loadWpStore();
  return s.items.find((i) => i.id === s.activeId) ?? null;
}

function emitConnectionChange(): void {
  try {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  } catch {
    // 무시
  }
}

/** 접속 정보 추가/갱신 후 사용 중으로 지정 */
export function saveWpConnection(conn: Omit<SavedWpConnection, "id">): void {
  const id = connectionId(conn.url, conn.user);
  const s = loadWpStore();
  const item: SavedWpConnection = { ...conn, id };
  const items = s.items.some((i) => i.id === id)
    ? s.items.map((i) => (i.id === id ? item : i))
    : [...s.items, item];
  writeStore({ activeId: id, items });
}

export function setActiveWpConnection(id: string): void {
  const s = loadWpStore();
  if (!s.items.some((i) => i.id === id)) return;
  writeStore({ activeId: id, items: s.items });
}

export function removeWpConnection(id: string): void {
  const s = loadWpStore();
  const items = s.items.filter((i) => i.id !== id);
  const activeId = s.activeId === id ? (items[0]?.id ?? null) : s.activeId;
  writeStore({ activeId, items });
}

/** 사용 중인 연결 해제(목록에서 제거) — v1 호환 */
export function clearWpConnection(): void {
  const s = loadWpStore();
  if (s.activeId) removeWpConnection(s.activeId);
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
 * 사용 중인 접속 정보 훅. save/remove 호출 시 자동으로 최신값으로 갱신된다.
 * undefined = 확인 중(SSR/하이드레이션), null = 미연결, 객체 = 연결됨.
 */
export function useWpConnection(): SavedWpConnection | null | undefined {
  return useSyncExternalStore(subscribeConnection, loadWpConnection, () => SERVER_SNAPSHOT);
}

/** 저장된 사이트 전체 + 사용 중 id. undefined = 확인 중 */
export function useWpStore(): WpStore | undefined {
  return useSyncExternalStore(subscribeConnection, loadWpStore, () => SERVER_SNAPSHOT);
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

const NOT_CONNECTED = "워드프레스 연결이 필요해요. [연결 설정]에서 먼저 연결해 주세요.";

function authHeader(): Record<string, string> {
  const conn = loadWpConnection();
  if (!conn) throw new WpApiClientError(NOT_CONNECTED, 401);
  return {
    [WP_CONNECTION_HEADER]: encodeWpConnection({
      url: conn.url,
      user: conn.user,
      appPassword: conn.appPassword,
    }),
  };
}

async function handle<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new WpApiClientError(
      data?.error || "요청에 실패했어요. 잠시 후 다시 시도해 주세요.",
      res.status,
    );
  }
  return data;
}

/**
 * /api/wp/* 호출 래퍼. 사용 중인 접속 정보를 x-wp-connection 헤더로 동봉.
 * 실패 시 서버가 준 한국어 안내 메시지를 WpApiClientError 로 던진다.
 */
export async function wpApi<T>(
  path: string,
  init: { method?: string; json?: unknown } = {},
): Promise<T> {
  const res = await fetch(path, {
    method: init.method ?? (init.json !== undefined ? "POST" : "GET"),
    headers: {
      ...authHeader(),
      ...(init.json !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init.json !== undefined ? JSON.stringify(init.json) : undefined,
  });
  return handle<T>(res);
}

/** 멀티파트 업로드(대표 이미지) — Content-Type 은 브라우저가 boundary 와 함께 붙인다 */
export async function wpUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: authHeader(), body: form });
  return handle<T>(res);
}

/** WP의 GMT 시각("YYYY-MM-DDTHH:mm:ss") → 사용자 로컬 표기 */
export function formatWpDate(dateGmt: string): string {
  if (!dateGmt) return "-";
  const iso = /Z|[+-]\d{2}:\d{2}$/.test(dateGmt) ? dateGmt : `${dateGmt}Z`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return dateGmt;
  return d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

/** WP의 GMT 시각이 이미 지났는지(예약 지연 감지용) */
export function isWpDatePast(dateGmt: string): boolean {
  if (!dateGmt) return false;
  const iso = /Z|[+-]\d{2}:\d{2}$/.test(dateGmt) ? dateGmt : `${dateGmt}Z`;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) && t < Date.now();
}
