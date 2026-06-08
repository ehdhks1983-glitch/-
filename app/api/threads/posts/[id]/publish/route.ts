// app/api/threads/posts/[id]/publish/route.ts  [신규]
// POST: 해당 게시물을 "지금" 공식 API로 발행(수동). 소유자만. 일일 안전 한도 적용.
//   - 이미 발행/발행중인 글은 거부. 성공 시 published, 실패 시 failed 로 기록.

import { NextResponse } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import {
  getMyPostById,
  getMyAccountWithToken,
  countPublishedSince,
  updateMyPost,
  markPublished,
  markFailed,
} from "@/lib/threads/db";
import { publishOne } from "@/lib/threads/publish";
import { THREADS_DAILY_CAP } from "@/lib/threads/config";

export const runtime = "nodejs";
export const maxDuration = 60;

type Ctx = { params: Promise<{ id: string }> };

export async function POST(_req: Request, ctx: Ctx) {
  const authed = await requireThreadsUser({ requireThreads: true });
  if (!isAuthed(authed)) return authed;
  const { supabase, user } = authed;
  const { id } = await ctx.params;

  try {
    const post = await getMyPostById(supabase, id, user.id);
    if (!post) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    if (post.status === "published" || post.status === "publishing") {
      return NextResponse.json({ error: "이미 발행됐거나 발행 중이에요." }, { status: 409 });
    }

    const account = await getMyAccountWithToken(supabase, user.id);
    if (!account) {
      return NextResponse.json({ error: "먼저 Threads 계정을 연결해 주세요." }, { status: 400 });
    }

    // 일일 안전 한도(계정당). Meta 상한(250)보다 훨씬 보수적인 기본값.
    const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const usedToday = await countPublishedSince(supabase, account.id, since);
    if (usedToday >= THREADS_DAILY_CAP) {
      return NextResponse.json(
        { error: `오늘 발행 한도(${THREADS_DAILY_CAP}개)에 도달했어요. 내일 다시 시도해 주세요.` },
        { status: 429 },
      );
    }

    // 발행중 표시(중복 발행 방지) → 발행 → 결과 기록
    await updateMyPost(supabase, id, user.id, { status: "publishing" });
    try {
      const mediaId = await publishOne({
        threadsUserId: account.threads_user_id,
        accessToken: account.access_token,
        text: post.text,
        mediaType: post.media_type,
        imageUrl: post.image_url,
      });
      await markPublished(supabase, id, mediaId);
    } catch (pubErr) {
      const msg = pubErr instanceof Error ? pubErr.message : String(pubErr);
      await markFailed(supabase, id, msg);
      console.error("[api/threads/posts/:id/publish] 발행 실패:", msg);
      return NextResponse.json({ error: "발행에 실패했어요. 큐에서 상태를 확인해 주세요." }, { status: 502 });
    }

    const updated = await getMyPostById(supabase, id, user.id);
    return NextResponse.json({ post: updated });
  } catch (err) {
    console.error("[api/threads/posts/:id/publish] 오류:", err);
    return NextResponse.json({ error: "발행 처리 중 문제가 발생했어요." }, { status: 500 });
  }
}
