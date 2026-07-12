// lib/wp/client.ts  [신규 — 워드프레스 자동 발행] ※ 서버 전용(guard가 node:dns 사용)
// WP REST API 호출의 단일 통로. 인증(Basic/응용 프로그램 비밀번호)·타임아웃·에러 정규화 담당.
// 고정 링크(퍼머링크)가 꺼진 사이트를 위해 /wp-json 실패 시 ?rest_route= 로 1회 폴백한다.
// 리다이렉트는 따라가지 않는다(SSRF 우회 방지) — 사용자에게 최종 주소 입력을 안내.

import { toBase64Utf8 } from "./connection";
import { assertPublicSiteUrl } from "./guard";
import type {
  WpCategory,
  WpConnection,
  WpNewPost,
  WpPostStatus,
  WpPostSummary,
} from "./types";

/** 호출 동작 파라미터(매직넘버 금지 → 여기로) */
const WP_CONFIG = {
  requestTimeoutMs: 20_000,
  /** 카테고리 전체 조회 시 페이지 상한(100개/페이지 × 10 = 1,000개) */
  maxCategoryPages: 10,
  categoryPerPage: 100,
  postsPerPage: 20,
  maxTags: 10,
};

/** WP가 돌려준 에러(HTTP 상태 + WP 에러 코드/메시지) */
export class WpApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public data?: unknown,
  ) {
    super(message);
  }
}

interface WpFetchOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
}

interface WpFetchResult<T> {
  data: T;
  headers: Headers;
}

function buildRestUrl(siteUrl: string, path: string, queryFallback: boolean): string {
  if (!queryFallback) return `${siteUrl}/wp-json${path}`;
  // 고정 링크 미사용 사이트: /?rest_route=/wp/v2/...&나머지쿼리
  const [pathname, query] = path.split("?", 2);
  return `${siteUrl}/?rest_route=${pathname}${query ? `&${query}` : ""}`;
}

function tryParseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** 모든 WP 호출의 공통 경로. path는 "/wp/v2/..." 형태(쿼리 포함 가능). */
async function wpFetch<T>(
  conn: WpConnection,
  path: string,
  opts: WpFetchOptions = {},
): Promise<WpFetchResult<T>> {
  await assertPublicSiteUrl(conn.url);

  const auth = `Basic ${toBase64Utf8(`${conn.user}:${conn.appPassword}`)}`;

  const attempt = async (queryFallback: boolean) => {
    const res = await fetch(buildRestUrl(conn.url, path, queryFallback), {
      method: opts.method ?? "GET",
      headers: {
        Authorization: auth,
        Accept: "application/json",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(WP_CONFIG.requestTimeoutMs),
    });
    if (res.status >= 300 && res.status < 400) {
      throw new WpApiError(
        res.status,
        "redirected",
        "사이트가 다른 주소로 이동(리다이렉트)하고 있어요. www 유무까지 정확한 최종 주소를 입력해 주세요.",
      );
    }
    const text = await res.text();
    return { res, parsed: tryParseJson(text) };
  };

  // 1차: /wp-json → 응답이 JSON이 아니면(HTML 404 등) 2차: ?rest_route=
  let { res, parsed } = await attempt(false);
  if (parsed === undefined) {
    ({ res, parsed } = await attempt(true));
  }
  if (parsed === undefined) {
    throw new WpApiError(
      res.status || 502,
      "invalid_response",
      "REST API 응답을 읽을 수 없어요. 주소가 워드프레스 사이트인지, REST API가 차단되지 않았는지 확인해 주세요.",
    );
  }

  if (!res.ok) {
    const e = parsed as { code?: unknown; message?: unknown; data?: unknown };
    throw new WpApiError(
      res.status,
      typeof e.code === "string" ? e.code : `http_${res.status}`,
      typeof e.message === "string" ? e.message.replace(/<[^>]*>/g, "") : "요청이 거부되었어요.",
      e.data,
    );
  }

  return { data: parsed as T, headers: res.headers };
}

// ───────────────────────── 연결 확인 ─────────────────────────

export interface WpSiteInfo {
  siteName: string;
  siteUrl: string;
  userName: string;
}

/** 연결 테스트: REST 인덱스(사이트 이름) + users/me(인증 확인)를 함께 조회. */
export async function testConnection(conn: WpConnection): Promise<WpSiteInfo> {
  const me = await wpFetch<{ name?: string; slug?: string }>(conn, "/wp/v2/users/me?context=edit");

  let siteName = "";
  try {
    const index = await wpFetch<{ name?: string }>(conn, "/");
    siteName = typeof index.data.name === "string" ? index.data.name : "";
  } catch {
    // 인덱스 조회 실패는 치명적이지 않음(인증은 이미 확인됨)
  }

  return {
    siteName: siteName || conn.url,
    siteUrl: conn.url,
    userName: me.data.name || me.data.slug || conn.user,
  };
}

// ───────────────────────── 카테고리 ─────────────────────────

interface RawCategory {
  id: number;
  name?: string;
  slug?: string;
  description?: string;
  parent?: number;
  count?: number;
}

function mapCategory(raw: RawCategory): WpCategory {
  return {
    id: raw.id,
    name: raw.name ?? "",
    slug: raw.slug ?? "",
    description: raw.description ?? "",
    parent: raw.parent ?? 0,
    count: raw.count ?? 0,
  };
}

/** 전체 카테고리 조회(페이지네이션 순회) */
export async function listCategories(conn: WpConnection): Promise<WpCategory[]> {
  const out: WpCategory[] = [];
  for (let page = 1; page <= WP_CONFIG.maxCategoryPages; page++) {
    const { data, headers } = await wpFetch<RawCategory[]>(
      conn,
      `/wp/v2/categories?per_page=${WP_CONFIG.categoryPerPage}&page=${page}&orderby=name&order=asc&hide_empty=false`,
    );
    out.push(...data.map(mapCategory));
    const totalPages = Number(headers.get("x-wp-totalpages") ?? "1");
    if (!Number.isFinite(totalPages) || page >= totalPages) break;
  }
  return out;
}

export interface CategoryFields {
  name?: string;
  slug?: string;
  description?: string;
  parent?: number;
}

export async function createCategory(conn: WpConnection, fields: CategoryFields): Promise<WpCategory> {
  const { data } = await wpFetch<RawCategory>(conn, "/wp/v2/categories", {
    method: "POST",
    body: fields,
  });
  return mapCategory(data);
}

export async function updateCategory(
  conn: WpConnection,
  id: number,
  fields: CategoryFields,
): Promise<WpCategory> {
  const { data } = await wpFetch<RawCategory>(conn, `/wp/v2/categories/${id}`, {
    method: "POST",
    body: fields,
  });
  return mapCategory(data);
}

/** 카테고리 삭제. (카테고리는 휴지통이 없어 force=true 필수 — 글은 기본 카테고리로 이동) */
export async function deleteCategory(conn: WpConnection, id: number): Promise<void> {
  await wpFetch(conn, `/wp/v2/categories/${id}?force=true`, { method: "DELETE" });
}

// ───────────────────────── 글 ─────────────────────────

interface RawPost {
  id: number;
  title?: { raw?: string; rendered?: string };
  status?: string;
  date_gmt?: string;
  link?: string;
  categories?: number[];
}

function mapPost(raw: RawPost): WpPostSummary {
  const title =
    raw.title?.raw ?? (raw.title?.rendered ?? "").replace(/<[^>]*>/g, "");
  return {
    id: raw.id,
    title: title || "(제목 없음)",
    status: (raw.status ?? "draft") as WpPostStatus,
    dateGmt: raw.date_gmt ?? "",
    link: raw.link ?? "",
    categories: Array.isArray(raw.categories) ? raw.categories : [],
  };
}

export interface ListPostsQuery {
  /** 콤마 없이 배열로 — 내부에서 조인 */
  statuses: WpPostStatus[];
  page: number;
  search?: string;
  categoryId?: number;
}

export interface ListPostsResult {
  posts: WpPostSummary[];
  total: number;
  totalPages: number;
}

export async function listPosts(conn: WpConnection, q: ListPostsQuery): Promise<ListPostsResult> {
  const params = new URLSearchParams({
    context: "edit",
    per_page: String(WP_CONFIG.postsPerPage),
    page: String(q.page),
    orderby: "date",
    order: "desc",
    status: q.statuses.join(","),
  });
  if (q.search) params.set("search", q.search);
  if (q.categoryId) params.set("categories", String(q.categoryId));

  const { data, headers } = await wpFetch<RawPost[]>(conn, `/wp/v2/posts?${params.toString()}`);
  return {
    posts: data.map(mapPost),
    total: Number(headers.get("x-wp-total") ?? "0") || 0,
    totalPages: Number(headers.get("x-wp-totalpages") ?? "1") || 1,
  };
}

/** Date → WP가 받는 GMT 표기("YYYY-MM-DDTHH:mm:ss") */
export function toWpDateGmt(d: Date): string {
  return d.toISOString().slice(0, 19);
}

/** 태그 이름 → 태그 id. 없으면 만들고, 이미 있으면(term_exists) 기존 id를 쓴다. */
async function ensureTagIds(conn: WpConnection, names: string[]): Promise<number[]> {
  const unique = [...new Set(names.map((n) => n.trim()).filter(Boolean))].slice(0, WP_CONFIG.maxTags);
  const ids: number[] = [];
  for (const name of unique) {
    try {
      const { data } = await wpFetch<{ id: number }>(conn, "/wp/v2/tags", {
        method: "POST",
        body: { name },
      });
      ids.push(data.id);
    } catch (err) {
      if (err instanceof WpApiError && err.code === "term_exists") {
        const termId = (err.data as { term_id?: unknown } | undefined)?.term_id;
        if (typeof termId === "number") {
          ids.push(termId);
          continue;
        }
      }
      // 태그 하나 실패로 발행 전체를 막지 않는다(태그는 부가 정보).
      if (process.env.NODE_ENV !== "production") {
        console.warn(`[wp] 태그 생성 실패 — 건너뜀: ${name}`);
      }
    }
  }
  return ids;
}

export interface CreatedPost {
  id: number;
  link: string;
  status: WpPostStatus;
  dateGmt: string;
  title: string;
}

export async function createPost(conn: WpConnection, input: WpNewPost): Promise<CreatedPost> {
  const tagIds = input.tags.length ? await ensureTagIds(conn, input.tags) : [];

  const body: Record<string, unknown> = {
    title: input.title,
    content: input.html,
    excerpt: input.excerpt,
    status: input.status,
  };
  if (input.categoryId) body.categories = [input.categoryId];
  if (tagIds.length) body.tags = tagIds;
  if (input.status === "future" && input.dateGmt) body.date_gmt = input.dateGmt;

  const { data } = await wpFetch<RawPost>(conn, "/wp/v2/posts", { method: "POST", body });
  const mapped = mapPost(data);
  return {
    id: mapped.id,
    link: mapped.link,
    status: mapped.status,
    dateGmt: mapped.dateGmt,
    title: mapped.title,
  };
}

/** 예약/임시 글을 지금 즉시 발행 상태로 전환 */
export async function publishPostNow(conn: WpConnection, id: number): Promise<WpPostSummary> {
  const { data } = await wpFetch<RawPost>(conn, `/wp/v2/posts/${id}`, {
    method: "POST",
    body: { status: "publish", date_gmt: toWpDateGmt(new Date()) },
  });
  return mapPost(data);
}

/** 글 삭제(휴지통으로 이동) */
export async function trashPost(conn: WpConnection, id: number): Promise<void> {
  await wpFetch(conn, `/wp/v2/posts/${id}`, { method: "DELETE" });
}
