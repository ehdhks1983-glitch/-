// app/api/threads/posts/route.ts  [신규]
// GET: 내 발행 큐 목록.
// POST: 초안 저장(draft) 또는 예약(scheduled). 계정 연결 필수(account_id NOT NULL).
//   - status="scheduled" 면 미래 시각 scheduledAt 필수.
//   - mediaType="IMAGE" 면 공개 image_url 필수.

import { NextResponse } from "next/server";
import { requireThreadsUser, isAuthed } from "@/lib/threads/server";
import { getMyAccount, insertPost, selectMyPosts } from "@/lib/threads/db";
import { THREADS_MAX_TEXT } from "@/lib/threads/config";
import {
  cleanText,
  isValidText,
  parseMediaType,
  parseImageUrl,
  parseFutureISO,
} from "@/lib/threads/validate";

export const runtime = "nodejs";

export async function GET() {
  const ctx = await requireThreadsUser();
  if (!isAuthed(ctx)) return ctx;
  const { supabase, user } = ctx;

  try {
    const posts = await selectMyPosts(supabase, user.id);
    return NextResponse.json({ posts });
  } catch (err) {
    console.error("[api/threads/posts] GET 실패:", err);
    return NextResponse.json({ error: "목록을 불러오지 못했어요." }, { status: 500 });
  }
}

export async function POST(req: Request) {
  const ctx = await requireThreadsUser({ requireThreads: true });
  if (!isAuthed(ctx)) return ctx;
  const { supabase, user } = ctx;

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }

  const text = cleanText(body.text);
  if (!isValidText(text)) {
    return NextResponse.json(
      { error: `글 내용을 ${THREADS_MAX_TEXT}자 이내로 입력해 주세요.` },
      { status: 400 },
    );
  }

  const mediaType = parseMediaType(body.mediaType);
  const imageUrl = parseImageUrl(body.imageUrl);
  if (mediaType === "IMAGE" && !imageUrl) {
    return NextResponse.json({ error: "이미지 글은 공개 이미지 URL이 필요해요." }, { status: 400 });
  }

  const wantSchedule = body.status === "scheduled";
  let scheduledAt: string | null = null;
  if (wantSchedule) {
    scheduledAt = parseFutureISO(body.scheduledAt);
    if (!scheduledAt) {
      return NextResponse.json({ error: "예약 시각은 현재 이후로 정해 주세요." }, { status: 400 });
    }
  }

  try {
    const account = await getMyAccount(supabase, user.id);
    if (!account) {
      return NextResponse.json(
        { error: "먼저 Threads 계정을 연결해 주세요." },
        { status: 400 },
      );
    }

    const post = await insertPost(supabase, user.id, {
      accountId: account.id,
      text,
      mediaType,
      imageUrl,
      status: wantSchedule ? "scheduled" : "draft",
      scheduledAt,
    });
    return NextResponse.json({ post });
  } catch (err) {
    console.error("[api/threads/posts] POST 실패:", err);
    return NextResponse.json({ error: "저장에 실패했어요. 잠시 후 다시 시도해 주세요." }, { status: 500 });
  }
}
