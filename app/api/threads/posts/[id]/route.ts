// app/api/threads/posts/[id]/route.ts  [신규]
// PATCH: 초안 수정 / 예약(draft→scheduled) / 예약변경 / 취소(→canceled). 소유자만.
//   - 클라이언트가 지정 가능한 status 는 draft|scheduled|canceled 뿐(발행/실패 상태는 서버만 설정).
// DELETE: 게시물 삭제.

import { NextResponse } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import { getMyPostById, updateMyPost, deleteMyPost, type PostPatch } from "@/lib/threads/db";
import { THREADS_MAX_TEXT } from "@/lib/threads/config";
import { cleanText, isValidText, parseFutureISO } from "@/lib/threads/validate";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

const CLIENT_STATUSES = new Set(["draft", "scheduled", "canceled"]);

export async function PATCH(req: Request, ctx: Ctx) {
  const authed = await requireThreadsUser();
  if (!isAuthed(authed)) return authed;
  const { supabase, user } = authed;
  const { id } = await ctx.params;

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }

  const patch: PostPatch = {};

  if (typeof body.text === "string") {
    const text = cleanText(body.text);
    if (!isValidText(text)) {
      return NextResponse.json(
        { error: `글 내용을 ${THREADS_MAX_TEXT}자 이내로 입력해 주세요.` },
        { status: 400 },
      );
    }
    patch.text = text;
  }

  if (typeof body.status === "string") {
    if (!CLIENT_STATUSES.has(body.status)) {
      return NextResponse.json({ error: "허용되지 않은 상태예요." }, { status: 400 });
    }
    patch.status = body.status as PostPatch["status"];
    if (body.status === "scheduled") {
      const when = parseFutureISO(body.scheduledAt);
      if (!when) {
        return NextResponse.json({ error: "예약 시각은 현재 이후로 정해 주세요." }, { status: 400 });
      }
      patch.scheduledAt = when;
    }
    if (body.status === "canceled" || body.status === "draft") {
      patch.scheduledAt = null; // 예약 해제
    }
  } else if (body.scheduledAt !== undefined) {
    // 상태 변경 없이 예약 시각만 조정
    const when = parseFutureISO(body.scheduledAt);
    if (!when) {
      return NextResponse.json({ error: "예약 시각은 현재 이후로 정해 주세요." }, { status: 400 });
    }
    patch.scheduledAt = when;
  }

  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "변경할 내용이 없어요." }, { status: 400 });
  }

  try {
    const post = await updateMyPost(supabase, id, user.id, patch);
    if (!post) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    return NextResponse.json({ post });
  } catch (err) {
    console.error("[api/threads/posts/:id] PATCH 실패:", err);
    return NextResponse.json({ error: "저장에 실패했어요." }, { status: 500 });
  }
}

export async function DELETE(_req: Request, ctx: Ctx) {
  const authed = await requireThreadsUser();
  if (!isAuthed(authed)) return authed;
  const { supabase, user } = authed;
  const { id } = await ctx.params;

  try {
    const existing = await getMyPostById(supabase, id, user.id);
    if (!existing) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    await deleteMyPost(supabase, id, user.id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/threads/posts/:id] DELETE 실패:", err);
    return NextResponse.json({ error: "삭제에 실패했어요." }, { status: 500 });
  }
}
