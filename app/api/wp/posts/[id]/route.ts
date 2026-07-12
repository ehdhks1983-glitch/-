// app/api/wp/posts/[id]/route.ts  [신규 — 워드프레스 자동 발행]
// PATCH: { publishNow: true } → 예약/임시 글을 즉시 발행 / DELETE: 휴지통으로 이동.

import { NextResponse } from "next/server";
import { publishPostNow, trashPost } from "@/lib/wp/client";
import {
  readConnection,
  needConnection,
  badRequest,
  tooMany,
  wpErrorResponse,
} from "@/lib/wp/serverUtil";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const WP_PROXY_LIMIT = 90;
const WP_PROXY_WINDOW_MS = 60_000;

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
  if (!id) return badRequest("글 id가 올바르지 않습니다.");

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return badRequest("요청 형식이 올바르지 않습니다.");
  }

  if (body.publishNow !== true) {
    return badRequest("지원하지 않는 변경 요청입니다.");
  }

  try {
    const post = await publishPostNow(conn, id);
    return NextResponse.json({ post });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/posts PATCH");
  }
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (limited(req)) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  const id = parseId((await params).id);
  if (!id) return badRequest("글 id가 올바르지 않습니다.");

  try {
    await trashPost(conn, id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/posts DELETE");
  }
}
