// lib/wp/connection.ts  [신규 — 워드프레스 자동 발행]
// 접속 정보를 요청 헤더 하나에 실어 나르는 코덱. 브라우저·Node 양쪽에서 동작한다.
// 헤더는 ISO-8859-1만 안전하므로 UTF-8 JSON → base64 로 감싼다(한글 아이디/주소 대응).

import type { WpConnection } from "./types";

/** 접속 정보를 담는 커스텀 헤더 이름 */
export const WP_CONNECTION_HEADER = "x-wp-connection";

/** 입력 길이 상한(폭주/오용 방지) */
export const WP_CONNECTION_LIMITS = {
  url: 300,
  user: 100,
  appPassword: 200,
};

/** UTF-8 문자열 → base64 (btoa는 Latin-1 전용이라 바이트 단위로 우회) */
export function toBase64Utf8(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

/** base64 → UTF-8 문자열 */
export function fromBase64Utf8(b64: string): string {
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** 접속 정보 → 헤더 값 */
export function encodeWpConnection(conn: WpConnection): string {
  return toBase64Utf8(
    JSON.stringify({ url: conn.url, user: conn.user, appPassword: conn.appPassword }),
  );
}

/** 헤더 값 → 접속 정보. 형식이 어긋나면 null(호출부가 401 처리). */
export function decodeWpConnection(header: string): WpConnection | null {
  try {
    const raw = JSON.parse(fromBase64Utf8(header)) as Record<string, unknown>;
    const url = typeof raw.url === "string" ? raw.url.trim() : "";
    const user = typeof raw.user === "string" ? raw.user.trim() : "";
    const appPassword = typeof raw.appPassword === "string" ? raw.appPassword.trim() : "";
    if (!url || !user || !appPassword) return null;
    if (
      url.length > WP_CONNECTION_LIMITS.url ||
      user.length > WP_CONNECTION_LIMITS.user ||
      appPassword.length > WP_CONNECTION_LIMITS.appPassword
    ) {
      return null;
    }
    return { url, user, appPassword };
  } catch {
    return null;
  }
}
