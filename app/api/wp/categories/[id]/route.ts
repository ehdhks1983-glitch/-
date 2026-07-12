// app/api/wp/categories/[id]/route.ts  [신규 — 워드프레스 자동 발행]
// PATCH: 카테고리 수정 / DELETE: 카테고리 삭제(소속 글은 WP 기본 카테고리로 이동).

import { NextResponse } from "next/server";
import { updateCategory, deleteCategory } from "@/lib/wp/client";
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

const WP_PROXY_LIMIT = 90;
const WP_PROXY_WINDOW_MS = 60_000;

const FIELD_LIMITS = { name: 100, slug: 100, description: 500 };

function limited(req: Request): boolean {
  sweep();
  return !rateLimit(clientKey(req, "wp-proxy"), WP_PROXY_LIMIT, WP_PROXY_WINDOW_MS).ok;
}

function parseId(raw: string): number | null {
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (limited(req)) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  const id = parseId((await params).id);
  if (!id) return badRequest("카테고리 id가 올바르지 않습니다.");

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return badRequest("요청 형식이 올바르지 않습니다.");
  }

  const name = strField(body, "name", FIELD_LIMITS.name);
  const slug = strField(body, "slug", FIELD_LIMITS.slug);
  const description = strField(body, "description", FIELD_LIMITS.description);
  const parent = intField(body, "parent");

  if (!name && !slug && !description && parent === undefined) {
    return badRequest("변경할 내용이 없습니다.");
  }

  try {
    const category = await updateCategory(conn, id, {
      ...(name ? { name } : {}),
      ...(slug ? { slug } : {}),
      // 설명은 비우는 것도 허용
      ...("description" in body ? { description } : {}),
      ...(parent !== undefined ? { parent } : {}),
    });
    return NextResponse.json({ category });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/categories PATCH");
  }
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (limited(req)) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  const id = parseId((await params).id);
  if (!id) return badRequest("카테고리 id가 올바르지 않습니다.");

  try {
    await deleteCategory(conn, id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/categories DELETE");
  }
}
