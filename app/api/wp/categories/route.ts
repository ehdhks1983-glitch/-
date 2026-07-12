// app/api/wp/categories/route.ts  [신규 — 워드프레스 자동 발행]
// GET: 전체 카테고리 목록 / POST: 카테고리 생성. 무상태 프록시(접속 정보는 헤더).

import { NextResponse } from "next/server";
import { listCategories, createCategory } from "@/lib/wp/client";
import {
  readConnection,
  needConnection,
  badRequest,
  tooMany,
  wpErrorResponse,
  strField,
  intField,
} from "@/lib/wp/serverUtil";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const WP_PROXY_LIMIT = 90; // 분당 프록시 호출(IP 기준)
const WP_PROXY_WINDOW_MS = 60_000;

const FIELD_LIMITS = { name: 100, slug: 100, description: 500 };

function limited(req: Request): boolean {
  sweep();
  return !rateLimit(clientKey(req, "wp-proxy"), WP_PROXY_LIMIT, WP_PROXY_WINDOW_MS).ok;
}

export async function GET(req: Request) {
  if (limited(req)) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  try {
    const categories = await listCategories(conn);
    return NextResponse.json({ categories });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/categories GET");
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

  const name = strField(body, "name", FIELD_LIMITS.name);
  if (!name) return badRequest("카테고리명을 입력해 주세요.");

  const slug = strField(body, "slug", FIELD_LIMITS.slug);
  const description = strField(body, "description", FIELD_LIMITS.description);
  const parent = intField(body, "parent");

  try {
    const category = await createCategory(conn, {
      name,
      ...(slug ? { slug } : {}),
      ...(description ? { description } : {}),
      ...(parent !== undefined ? { parent } : {}),
    });
    return NextResponse.json({ category });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/categories POST");
  }
}
