// lib/threads/db.ts  [신규] — 서버 전용 Threads 데이터 헬퍼.
// 호출자가 만든 Supabase 클라이언트를 넘긴다(소유자 세션 = createSupabaseServer, 크론 = createSupabaseAdmin).
// 보안 원칙: access_token 은 "토큰이 필요한 서버 작업"에서만 select. UI용 조회는 토큰 컬럼을 절대 포함하지 않는다.

import type { SupabaseClient } from "@supabase/supabase-js";

export type ThreadsPostStatus =
  | "draft"
  | "scheduled"
  | "publishing"
  | "published"
  | "failed"
  | "canceled";

export type ThreadsMediaType = "TEXT" | "IMAGE";

/** UI/상태 표시용 계정 정보(토큰 제외). */
export interface ThreadsAccountPublic {
  id: string;
  threads_user_id: string;
  username: string;
  token_expires_at: string | null;
  created_at: string;
}

/** 토큰 포함 계정(서버 발행 작업 전용). */
export interface ThreadsAccountWithToken extends ThreadsAccountPublic {
  access_token: string;
}

export interface ThreadsPostRow {
  id: string;
  owner: string;
  account_id: string;
  text: string;
  media_type: ThreadsMediaType;
  image_url: string | null;
  status: ThreadsPostStatus;
  scheduled_at: string | null;
  published_at: string | null;
  threads_media_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

const PUBLIC_COLS = "id, threads_user_id, username, token_expires_at, created_at";

// ───────────────────────── 계정 ─────────────────────────

/** 내 연결 계정(토큰 제외). 없으면 null. */
export async function getMyAccount(
  supabase: SupabaseClient,
  owner: string,
): Promise<ThreadsAccountPublic | null> {
  const { data, error } = await supabase
    .from("threads_accounts")
    .select(PUBLIC_COLS)
    .eq("owner", owner)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ThreadsAccountPublic) ?? null;
}

/** 내 연결 계정(토큰 포함). 발행 등 토큰이 필요한 서버 작업에서만 사용. */
export async function getMyAccountWithToken(
  supabase: SupabaseClient,
  owner: string,
): Promise<ThreadsAccountWithToken | null> {
  const { data, error } = await supabase
    .from("threads_accounts")
    .select(`${PUBLIC_COLS}, access_token`)
    .eq("owner", owner)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ThreadsAccountWithToken) ?? null;
}

export interface UpsertAccountInput {
  threadsUserId: string;
  username: string;
  accessToken: string;
  tokenExpiresAt: string | null;
}

/** 계정 연결/갱신(owner 기준 upsert). */
export async function upsertAccount(
  supabase: SupabaseClient,
  owner: string,
  input: UpsertAccountInput,
): Promise<ThreadsAccountPublic> {
  const { data, error } = await supabase
    .from("threads_accounts")
    .upsert(
      {
        owner,
        threads_user_id: input.threadsUserId,
        username: input.username,
        access_token: input.accessToken,
        token_expires_at: input.tokenExpiresAt,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "owner" },
    )
    .select(PUBLIC_COLS)
    .single();
  if (error) throw new Error(error.message);
  return data as ThreadsAccountPublic;
}

export async function deleteAccount(supabase: SupabaseClient, owner: string): Promise<void> {
  const { error } = await supabase.from("threads_accounts").delete().eq("owner", owner);
  if (error) throw new Error(error.message);
}

// ───────────────────────── 게시물(큐) ─────────────────────────

export interface NewPost {
  accountId: string;
  text: string;
  mediaType: ThreadsMediaType;
  imageUrl?: string | null;
  status: Extract<ThreadsPostStatus, "draft" | "scheduled">;
  scheduledAt?: string | null;
}

export async function insertPost(
  supabase: SupabaseClient,
  owner: string,
  input: NewPost,
): Promise<ThreadsPostRow> {
  const { data, error } = await supabase
    .from("threads_posts")
    .insert({
      owner,
      account_id: input.accountId,
      text: input.text,
      media_type: input.mediaType,
      image_url: input.imageUrl ?? null,
      status: input.status,
      scheduled_at: input.scheduledAt ?? null,
    })
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data as ThreadsPostRow;
}

export async function selectMyPosts(
  supabase: SupabaseClient,
  owner: string,
): Promise<ThreadsPostRow[]> {
  const { data, error } = await supabase
    .from("threads_posts")
    .select("*")
    .eq("owner", owner)
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as ThreadsPostRow[];
}

export async function getMyPostById(
  supabase: SupabaseClient,
  id: string,
  owner: string,
): Promise<ThreadsPostRow | null> {
  const { data, error } = await supabase
    .from("threads_posts")
    .select("*")
    .eq("id", id)
    .eq("owner", owner)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ThreadsPostRow) ?? null;
}

export interface PostPatch {
  text?: string;
  status?: ThreadsPostStatus;
  scheduledAt?: string | null;
  imageUrl?: string | null;
}

/** 내 게시물 수정(소유자만). 없으면 null. */
export async function updateMyPost(
  supabase: SupabaseClient,
  id: string,
  owner: string,
  patch: PostPatch,
): Promise<ThreadsPostRow | null> {
  const row: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (patch.text !== undefined) row.text = patch.text;
  if (patch.status !== undefined) row.status = patch.status;
  if (patch.scheduledAt !== undefined) row.scheduled_at = patch.scheduledAt;
  if (patch.imageUrl !== undefined) row.image_url = patch.imageUrl;

  const { data, error } = await supabase
    .from("threads_posts")
    .update(row)
    .eq("id", id)
    .eq("owner", owner)
    .select("*")
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ThreadsPostRow) ?? null;
}

export async function deleteMyPost(
  supabase: SupabaseClient,
  id: string,
  owner: string,
): Promise<void> {
  const { error } = await supabase.from("threads_posts").delete().eq("id", id).eq("owner", owner);
  if (error) throw new Error(error.message);
}

// ───────────────────────── 크론(service_role) 전용 ─────────────────────────

/** 발행 시각이 도래한 예약 게시물 + 해당 계정 토큰을 함께 조회. admin 클라이언트로만 호출. */
export interface DuePost extends ThreadsPostRow {
  account: { id: string; threads_user_id: string; access_token: string } | null;
}

export async function getDuePosts(
  admin: SupabaseClient,
  nowIso: string,
  limit: number,
): Promise<DuePost[]> {
  const { data, error } = await admin
    .from("threads_posts")
    .select("*, account:threads_accounts ( id, threads_user_id, access_token )")
    .eq("status", "scheduled")
    .lte("scheduled_at", nowIso)
    .order("scheduled_at", { ascending: true })
    .limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as DuePost[];
}

/** 발행 직전 원자적 클레임: scheduled → publishing. 이미 누가 가져갔으면 false. */
export async function claimForPublish(admin: SupabaseClient, id: string): Promise<boolean> {
  const { data, error } = await admin
    .from("threads_posts")
    .update({ status: "publishing", updated_at: new Date().toISOString() })
    .eq("id", id)
    .eq("status", "scheduled")
    .select("id")
    .maybeSingle();
  if (error) throw new Error(error.message);
  return Boolean(data);
}

export async function markPublished(
  admin: SupabaseClient,
  id: string,
  mediaId: string,
): Promise<void> {
  const { error } = await admin
    .from("threads_posts")
    .update({
      status: "published",
      threads_media_id: mediaId,
      published_at: new Date().toISOString(),
      error: null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", id);
  if (error) throw new Error(error.message);
}

export async function markFailed(admin: SupabaseClient, id: string, message: string): Promise<void> {
  const { error } = await admin
    .from("threads_posts")
    .update({ status: "failed", error: message.slice(0, 500), updated_at: new Date().toISOString() })
    .eq("id", id);
  if (error) throw new Error(error.message);
}

/** 계정별 최근 발행 건수(일일 안전 한도 체크용). */
export async function countPublishedSince(
  supabase: SupabaseClient,
  accountId: string,
  sinceIso: string,
): Promise<number> {
  const { count, error } = await supabase
    .from("threads_posts")
    .select("id", { count: "exact", head: true })
    .eq("account_id", accountId)
    .eq("status", "published")
    .gte("published_at", sinceIso);
  if (error) throw new Error(error.message);
  return count ?? 0;
}

/** 계정별 최근 24시간 발행 건수. 시간 계산을 컴포넌트 렌더 밖(lib)에서 수행. */
export async function countPublishedLast24h(
  supabase: SupabaseClient,
  accountId: string,
): Promise<number> {
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  return countPublishedSince(supabase, accountId, since);
}
