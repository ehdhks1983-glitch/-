// lib/wp/client.ts  [업데이트 — 워드프레스 자동 발행 v2] ※ 서버 전용(guard가 node:dns 사용)
// WP REST API 호출의 단일 통로. 인증(Basic/응용 프로그램 비밀번호)·타임아웃·에러 정규화 담당.
// 고정 링크(퍼머링크)가 꺼진 사이트를 위해 /wp-json 실패 시 ?rest_route= 로 1회 폴백한다.
// 리다이렉트는 따라가지 않는다(SSRF 우회 방지) — 사용자에게 최종 주소 입력을 안내.
// v2: SEO 플러그인 감지·사이트 타임존, 미디어 업로드(대표 이미지), 블록 마크업 전송,
//     슬러그·SEO 메타(Yoast/RankMath 키) 동시 전송.

import { toBase64Utf8 } from "./connection";
import { assertPublicSiteUrl } from "./guard";
import { htmlToBlocks } from "./blocks";
import type {
  SeoPlugin,
  WpCategory,
  WpConnection,
  WpNewPost,
  WpPostStatus,
  WpPostSummary,
  WpSeoFields,
} from "./types";

/** 호출 동작 파라미터(매직넘버 금지 → 여기로) */
const WP_CONFIG = {
  requestTimeoutMs: 20_000,
  uploadTimeoutMs: 60_000,
  /** 카테고리 전체 조회 시 페이지 상한(100개/페이지 × 10 = 1,000개) */
  maxCategoryPages: 10,
  categoryPerPage: 100,
  postsPerPage: 20,
  postsPerPageMax: 50,
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
  /** JSON 본문 */
  body?: unknown;
  /** 멀티파트 본문(폴백 재시도를 위해 매번 새로 만든다) */
  form?: () => FormData;
  timeoutMs?: number;
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
    const form = opts.form?.();
    const res = await fetch(buildRestUrl(conn.url, path, queryFallback), {
      method: opts.method ?? "GET",
      headers: {
        Authorization: auth,
        Accept: "application/json",
        ...(opts.body !== undefined && !form ? { "Content-Type": "application/json" } : {}),
      },
      body: form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(opts.timeoutMs ?? WP_CONFIG.requestTimeoutMs),
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
  /** REST 인덱스 namespaces 로 감지한 SEO 플러그인 */
  seoPlugin: SeoPlugin;
  /** 사이트 타임존(예: "Asia/Seoul"). 설정 안 됐으면 빈 문자열 */
  timezone: string;
  /** 사이트 GMT 오프셋(시간). 타임존 미설정 사이트용 */
  gmtOffset: number;
}

interface RestIndex {
  name?: string;
  namespaces?: string[];
  timezone_string?: string;
  gmt_offset?: number | string;
}

function detectSeoPlugin(namespaces: string[]): SeoPlugin {
  if (namespaces.some((n) => n.startsWith("yoast/"))) return "yoast";
  if (namespaces.some((n) => n.startsWith("rankmath/"))) return "rankmath";
  if (namespaces.some((n) => n.startsWith("aioseo/"))) return "aioseo";
  return null;
}

/** 연결 테스트: users/me(인증 확인) + REST 인덱스(사이트 이름·플러그인·타임존). */
export async function testConnection(conn: WpConnection): Promise<WpSiteInfo> {
  const me = await wpFetch<{ name?: string; slug?: string }>(conn, "/wp/v2/users/me?context=edit");

  let siteName = "";
  let seoPlugin: SeoPlugin = null;
  let timezone = "";
  let gmtOffset = 0;
  try {
    const { data } = await wpFetch<RestIndex>(conn, "/");
    siteName = typeof data.name === "string" ? data.name : "";
    seoPlugin = detectSeoPlugin(Array.isArray(data.namespaces) ? data.namespaces : []);
    timezone = typeof data.timezone_string === "string" ? data.timezone_string : "";
    const off = Number(data.gmt_offset);
    gmtOffset = Number.isFinite(off) ? off : 0;
  } catch {
    // 인덱스 조회 실패는 치명적이지 않음(인증은 이미 확인됨)
  }

  return {
    siteName: siteName || conn.url,
    siteUrl: conn.url,
    userName: me.data.name || me.data.slug || conn.user,
    seoPlugin,
    timezone,
    gmtOffset,
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

// ───────────────────────── 미디어(대표 이미지) ─────────────────────────

export interface UploadMediaInput {
  data: ArrayBuffer;
  filename: string;
  mimeType: string;
  altText?: string;
  title?: string;
}

export interface UploadedMedia {
  id: number;
  url: string;
}

/** 이미지 업로드 → 미디어 id (글 생성 시 featured_media 로 사용) */
export async function uploadMedia(conn: WpConnection, input: UploadMediaInput): Promise<UploadedMedia> {
  const { data } = await wpFetch<{ id: number; source_url?: string }>(conn, "/wp/v2/media", {
    method: "POST",
    form: () => {
      const fd = new FormData();
      fd.append("file", new Blob([input.data], { type: input.mimeType }), input.filename);
      if (input.altText) fd.append("alt_text", input.altText);
      if (input.title) fd.append("title", input.title);
      return fd;
    },
    timeoutMs: WP_CONFIG.uploadTimeoutMs,
  });
  return { id: data.id, url: data.source_url ?? "" };
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
  perPage?: number;
  search?: string;
  categoryId?: number;
}

export interface ListPostsResult {
  posts: WpPostSummary[];
  total: number;
  totalPages: number;
}

export async function listPosts(conn: WpConnection, q: ListPostsQuery): Promise<ListPostsResult> {
  const perPage = Math.min(Math.max(q.perPage ?? WP_CONFIG.postsPerPage, 1), WP_CONFIG.postsPerPageMax);
  const params = new URLSearchParams({
    context: "edit",
    per_page: String(perPage),
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

/**
 * SEO 메타 → Yoast·RankMath 양쪽 키로 동시 전송.
 * WP REST는 show_in_rest 로 등록되지 않은 meta 키를 조용히 무시하므로 양쪽을 보내도 안전하다.
 * (Yoast는 기본 등록, RankMath는 브리지 플러그인으로 등록 필요 — README 참고)
 */
function buildSeoMeta(seo: WpSeoFields): Record<string, string> {
  const m: Record<string, string> = {};
  if (seo.seoTitle) {
    m._yoast_wpseo_title = seo.seoTitle;
    m.rank_math_title = seo.seoTitle;
  }
  if (seo.metaDescription) {
    m._yoast_wpseo_metadesc = seo.metaDescription;
    m.rank_math_description = seo.metaDescription;
  }
  if (seo.focusKeyword) {
    m._yoast_wpseo_focuskw = seo.focusKeyword;
    m.rank_math_focus_keyword = seo.focusKeyword;
  }
  return m;
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
    content: input.format === "classic" ? input.html : htmlToBlocks(input.html),
    excerpt: input.excerpt,
    status: input.status,
  };
  if (input.categoryId) body.categories = [input.categoryId];
  if (tagIds.length) body.tags = tagIds;
  if (input.status === "future" && input.dateGmt) body.date_gmt = input.dateGmt;
  if (input.slug) body.slug = input.slug;
  if (input.featuredMediaId) body.featured_media = input.featuredMediaId;
  if (input.seo) {
    const meta = buildSeoMeta(input.seo);
    if (Object.keys(meta).length) body.meta = meta;
  }

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
