// lib/threads/client.ts  [신규]
// 공식 Threads Graph API 클라이언트(서버 전용). fetch 기반. 토큰/호스트는 config 에서만.
// 발행은 2단계: createContainer → publishContainer
//   (공식: POST /{user-id}/threads  →  POST /{user-id}/threads_publish)
// 이 모듈은 토큰을 인자로만 받고 저장하지 않는다(저장/조회는 lib/threads/db).

import { THREADS } from "./config";

export interface ShortLivedToken {
  accessToken: string;
  userId: string;
}
export interface LongLivedToken {
  accessToken: string;
  expiresInSec: number;
}
export interface ThreadsProfile {
  id: string;
  username: string;
}
export interface PublishingUsage {
  used: number;
  total: number;
}
export type ThreadsMediaType = "TEXT" | "IMAGE";

// ───────────────────────── OAuth 토큰 ─────────────────────────

/** 인가 코드 → 단기 토큰(+user_id). 토큰 엔드포인트는 버전 없는 루트 경로. */
export async function exchangeCodeForToken(code: string): Promise<ShortLivedToken> {
  const body = new URLSearchParams({
    client_id: THREADS.appId,
    client_secret: THREADS.appSecret,
    grant_type: "authorization_code",
    redirect_uri: THREADS.redirectUri,
    code,
  });
  const json = await readJson(
    await fetch(`${THREADS.graphHost}/oauth/access_token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    }),
  );
  return { accessToken: str(json.access_token), userId: str(json.user_id) };
}

/** 단기 → 장기 토큰(약 60일). */
export async function exchangeForLongLivedToken(shortToken: string): Promise<LongLivedToken> {
  const p = new URLSearchParams({
    grant_type: "th_exchange_token",
    client_secret: THREADS.appSecret,
    access_token: shortToken,
  });
  const json = await readJson(await fetch(`${THREADS.graphHost}/access_token?${p}`));
  return { accessToken: str(json.access_token), expiresInSec: num(json.expires_in) };
}

/** 장기 토큰 갱신(만료 임박 시). 24시간 이상 지난 토큰만 갱신 가능(공식 제약). */
export async function refreshLongLivedToken(longToken: string): Promise<LongLivedToken> {
  const p = new URLSearchParams({ grant_type: "th_refresh_token", access_token: longToken });
  const json = await readJson(await fetch(`${THREADS.graphHost}/refresh_access_token?${p}`));
  return { accessToken: str(json.access_token), expiresInSec: num(json.expires_in) };
}

// ───────────────────────── 프로필 / 발행 ─────────────────────────

/** 연결된 계정 프로필 조회(id, username). */
export async function getProfile(userId: string, token: string): Promise<ThreadsProfile> {
  const p = new URLSearchParams({ fields: "id,username", access_token: token });
  const json = await readJson(await fetch(`${THREADS.graphHost}/${enc(userId)}?${p}`));
  return { id: str(json.id) || userId, username: str(json.username) };
}

/** 1단계: 미디어 컨테이너 생성 → creation_id 반환. */
export async function createContainer(
  userId: string,
  token: string,
  input: { mediaType: ThreadsMediaType; text: string; imageUrl?: string },
): Promise<string> {
  const body = new URLSearchParams({ media_type: input.mediaType, access_token: token });
  if (input.text) body.set("text", input.text);
  if (input.mediaType === "IMAGE" && input.imageUrl) body.set("image_url", input.imageUrl);

  const json = await readJson(
    await fetch(`${THREADS.graphHost}/${enc(userId)}/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    }),
  );
  const id = str(json.id);
  if (!id) throw new Error("컨테이너 생성 응답에 id가 없습니다.");
  return id;
}

/** 2단계: 컨테이너 발행 → 게시물 미디어 id 반환. */
export async function publishContainer(
  userId: string,
  token: string,
  creationId: string,
): Promise<string> {
  const body = new URLSearchParams({ creation_id: creationId, access_token: token });
  const json = await readJson(
    await fetch(`${THREADS.graphHost}/${enc(userId)}/threads_publish`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    }),
  );
  const id = str(json.id);
  if (!id) throw new Error("발행 응답에 id가 없습니다.");
  return id;
}

/** 24시간 발행 사용량 조회(공식 한도 250 기준). 실패해도 호출부가 막히지 않도록 0/250 폴백. */
export async function getPublishingUsage(userId: string, token: string): Promise<PublishingUsage> {
  const p = new URLSearchParams({ fields: "quota_usage,config", access_token: token });
  const json = await readJson(
    await fetch(`${THREADS.graphHost}/${enc(userId)}/threads_publishing_limit?${p}`),
  );
  const row = Array.isArray(json.data) && isRecord(json.data[0]) ? json.data[0] : {};
  const config = isRecord(row.config) ? row.config : {};
  return { used: num(row.quota_usage), total: num(config.quota_total) || 250 };
}

// ───────────────────────── 내부 유틸 ─────────────────────────

type Json = Record<string, unknown>;

/** 응답 본문을 JSON 으로 파싱. 비-2xx 면 Meta 에러 메시지를 추출해 throw. */
async function readJson(res: Response): Promise<Json> {
  const text = await res.text();
  let json: Json = {};
  try {
    json = text ? (JSON.parse(text) as Json) : {};
  } catch {
    // 비-JSON 응답(예: HTML 오류 페이지) → 빈 객체로 두고 아래에서 상태코드로 판단
  }
  if (!res.ok) {
    const err = isRecord(json.error) ? json.error : {};
    const msg = str(err.message) || str(json.error_message) || `HTTP ${res.status}`;
    throw new Error(`Threads API 오류: ${msg}`);
  }
  return json;
}

function isRecord(v: unknown): v is Json {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}
function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function enc(v: string): string {
  return encodeURIComponent(v);
}
