// app/api/wp/generate/route.ts  [업데이트 — 워드프레스 자동 발행 v2]
// 주제/키워드 → AI 블로그 글 초안(제목·본문HTML·요약·태그·슬러그·SEO 메타). WP 호출은 없다(생성만).
// v2: 글 유형, 내부 링크 후보(연결된 사이트 호스트의 URL만) 지원.
// 기존 /api/generate 와 동일한 정책: 강한 rate limit + 친화적 에러 메시지.

import { NextResponse } from "next/server";
import { generatePost } from "@/lib/ai/generatePost";
import { POST_TYPES, type InternalLinkCandidate, type PostGenInput, type PostType } from "@/lib/wp/types";
import { siteHostOf } from "@/lib/wp/sanitizeHtml";
import { badRequest, tooMany, strField, readConnection } from "@/lib/wp/serverUtil";
import { sanitizeText } from "@/lib/sanitize";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const maxDuration = 60;

const GENERATE_LIMIT = 12; // 분당 생성 횟수(IP 기준) — 토큰 비용 폭주 방지
const GENERATE_WINDOW_MS = 60_000;

const FIELD_LIMITS = { topic: 100, categoryName: 60, tone: 40, extra: 500, linkTitle: 200, maxLinks: 30 };
const LENGTHS: PostGenInput["length"][] = ["short", "medium", "long"];

/** 내부 링크 후보 정규화: 연결된 사이트 호스트의 http(s) 주소만 남긴다 */
function normalizeLinks(input: unknown, siteHost: string | null): InternalLinkCandidate[] {
  if (!Array.isArray(input) || !siteHost) return [];
  const out: InternalLinkCandidate[] = [];
  for (const item of input) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    const title = sanitizeText(r.title, FIELD_LIMITS.linkTitle);
    const url = typeof r.url === "string" ? r.url.trim() : "";
    if (!title || !url) continue;
    try {
      const u = new URL(url);
      if (u.protocol !== "https:" && u.protocol !== "http:") continue;
      if (u.hostname.toLowerCase().replace(/^www\./, "") !== siteHost) continue;
      out.push({ title, url: u.href });
    } catch {
      // 잘못된 URL은 건너뜀
    }
    if (out.length >= FIELD_LIMITS.maxLinks) break;
  }
  return out;
}

export async function POST(req: Request) {
  sweep();
  const rl = rateLimit(clientKey(req, "wp-generate"), GENERATE_LIMIT, GENERATE_WINDOW_MS);
  if (!rl.ok) return tooMany();

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return badRequest("요청 형식이 올바르지 않습니다.");
  }

  const topic = strField(body, "topic", FIELD_LIMITS.topic);
  if (topic.length < 2) {
    return badRequest("어떤 주제(키워드)로 쓸지 2자 이상 입력해 주세요.");
  }

  const lengthRaw = strField(body, "length", 10);
  const length = LENGTHS.find((l) => l === lengthRaw) ?? "medium";

  const postTypeRaw = strField(body, "postType", 20);
  const postType = (Object.keys(POST_TYPES) as PostType[]).find((t) => t === postTypeRaw) ?? "info";

  // 연결 헤더가 있으면 그 사이트 호스트로만 내부 링크를 허용(없으면 링크 없는 글)
  const conn = readConnection(req);
  const siteHost = conn ? siteHostOf(conn.url) : null;
  const internalLinks = normalizeLinks(body.internalLinks, siteHost);

  const input: PostGenInput = {
    topic,
    length,
    postType,
    categoryName: strField(body, "categoryName", FIELD_LIMITS.categoryName) || undefined,
    tone: strField(body, "tone", FIELD_LIMITS.tone) || undefined,
    extra: strField(body, "extra", FIELD_LIMITS.extra) || undefined,
    ...(internalLinks.length ? { internalLinks } : {}),
    ...(siteHost ? { siteHost } : {}),
  };

  try {
    const post = await generatePost(input);
    return NextResponse.json({ post });
  } catch (err) {
    console.error("[api/wp/generate] 실패:", err);
    return NextResponse.json(
      { error: "글 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
