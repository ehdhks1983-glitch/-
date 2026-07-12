// app/api/wp/posts/route.ts  [신규 — 워드프레스 자동 발행]
// GET: 글 목록(상태 필터·검색·페이지) / POST: 글 등록(즉시·임시·예약).
// 본문 HTML은 서버에서 한 번 더 정화한 뒤 WP로 보낸다.

import { NextResponse } from "next/server";
import { createPost, listPosts } from "@/lib/wp/client";
import { sanitizeWpHtml, wpHtmlToText } from "@/lib/wp/sanitizeHtml";
import type { WpPostStatus } from "@/lib/wp/types";
import {
  readConnection,
  needConnection,
  badRequest,
  tooMany,
  wpErrorResponse,
  strField,
  intField,
} from "@/lib/wp/serverUtil";
import { sanitizeText } from "@/lib/sanitize";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const WP_PROXY_LIMIT = 90;
const WP_PROXY_WINDOW_MS = 60_000;

const ALL_STATUSES: WpPostStatus[] = ["publish", "future", "draft", "pending", "private"];
const FIELD_LIMITS = { title: 200, excerpt: 300, tag: 50, maxTags: 10, search: 100 };
/** 예약 시각 하한: 과거로 예약하면 WP가 즉시 발행해버리므로 서버에서 막는다(시계 오차 허용 2분). */
const SCHEDULE_MIN_AHEAD_MS = -2 * 60_000;

function limited(req: Request): boolean {
  sweep();
  return !rateLimit(clientKey(req, "wp-proxy"), WP_PROXY_LIMIT, WP_PROXY_WINDOW_MS).ok;
}

export async function GET(req: Request) {
  if (limited(req)) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  const sp = new URL(req.url).searchParams;

  const statusParam = sp.get("status") ?? "all";
  const statuses =
    statusParam === "all"
      ? ALL_STATUSES
      : ALL_STATUSES.filter((s) => statusParam.split(",").includes(s));
  if (statuses.length === 0) return badRequest("상태 필터가 올바르지 않습니다.");

  const pageRaw = Number(sp.get("page") ?? "1");
  const page = Number.isInteger(pageRaw) && pageRaw >= 1 && pageRaw <= 500 ? pageRaw : 1;
  const search = sanitizeText(sp.get("search") ?? "", FIELD_LIMITS.search);
  const categoryRaw = Number(sp.get("category") ?? "0");
  const categoryId =
    Number.isInteger(categoryRaw) && categoryRaw > 0 ? categoryRaw : undefined;

  try {
    const result = await listPosts(conn, {
      statuses,
      page,
      ...(search ? { search } : {}),
      ...(categoryId ? { categoryId } : {}),
    });
    return NextResponse.json(result);
  } catch (err) {
    return wpErrorResponse(err, "api/wp/posts GET");
  }
}

export async function POST(req: Request) {
  if (limited(req)) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return badRequest("요청 형식이 올바르지 않습니다.");
  }

  const title = strField(body, "title", FIELD_LIMITS.title);
  if (!title) return badRequest("제목을 입력해 주세요.");

  const html = sanitizeWpHtml(body.html);
  if (wpHtmlToText(html).length < 10) return badRequest("본문 내용이 너무 짧아요.");

  const statusRaw = strField(body, "status", 20);
  const status = ALL_STATUSES.find((s) => s === statusRaw);
  if (!status) return badRequest("발행 상태가 올바르지 않습니다.");

  let dateGmt: string | undefined;
  if (status === "future") {
    const raw = strField(body, "dateGmt", 30);
    const when = new Date(/Z|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`);
    if (!raw || Number.isNaN(when.getTime())) {
      return badRequest("예약 발행 시각을 입력해 주세요.");
    }
    if (when.getTime() - Date.now() < SCHEDULE_MIN_AHEAD_MS) {
      return badRequest("예약 시각이 이미 지났어요. 미래 시각으로 다시 선택해 주세요.");
    }
    dateGmt = when.toISOString().slice(0, 19);
  }

  const excerpt = strField(body, "excerpt", FIELD_LIMITS.excerpt);
  const categoryId = intField(body, "categoryId");
  const tags = Array.isArray(body.tags)
    ? body.tags
        .filter((t): t is string => typeof t === "string")
        .map((t) => sanitizeText(t, FIELD_LIMITS.tag))
        .filter(Boolean)
        .slice(0, FIELD_LIMITS.maxTags)
    : [];

  try {
    const post = await createPost(conn, {
      title,
      html,
      excerpt,
      status,
      ...(dateGmt ? { dateGmt } : {}),
      ...(categoryId ? { categoryId } : {}),
      tags,
    });
    return NextResponse.json({ post });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/posts POST");
  }
}
