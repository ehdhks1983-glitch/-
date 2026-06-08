// app/api/threads/cron/route.ts  [신규]
// 예약 발행 워커. 외부 스케줄러(Vercel Cron 등)가 주기적으로 호출.
//   - 보호: Authorization: Bearer <CRON_SECRET> 또는 ?secret=<CRON_SECRET>. CRON_SECRET 없으면 비활성(503).
//   - 발행시각 도래분을 원자적 클레임(scheduled→publishing) 후 공식 API로 발행. 일일 안전 한도 적용.
// 이벤트는 오지 않으므로(웹훅 아님) 스케줄러가 호출해야 한다 — README의 Cron 설정 참고.

import { NextResponse } from "next/server";
import { createSupabaseAdmin } from "@/lib/db/supabase-server";
import {
  isThreadsConfigured,
  THREADS_DAILY_CAP,
  THREADS_CRON_BATCH,
  THREADS_PUBLISHING_STALE_MIN,
} from "@/lib/threads/config";
import {
  getDuePosts,
  claimForPublish,
  markPublished,
  markFailed,
  countPublishedSince,
  requeueStalePublishing,
} from "@/lib/threads/db";
import { publishOne } from "@/lib/threads/publish";
import { refreshExpiringTokens } from "@/lib/threads/refresh";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function GET(req: Request) {
  return run(req);
}
export async function POST(req: Request) {
  return run(req);
}

async function run(req: Request): Promise<NextResponse> {
  const secret = process.env.CRON_SECRET ?? "";
  if (!secret) {
    return NextResponse.json({ error: "크론이 설정되지 않았어요(CRON_SECRET)." }, { status: 503 });
  }
  const auth = req.headers.get("authorization") ?? "";
  const qSecret = new URL(req.url).searchParams.get("secret") ?? "";
  if (auth !== `Bearer ${secret}` && qSecret !== secret) {
    return NextResponse.json({ error: "권한이 없어요." }, { status: 401 });
  }

  if (!isThreadsConfigured()) {
    return NextResponse.json({ error: "Threads 연동이 설정되지 않았어요." }, { status: 503 });
  }
  const admin = createSupabaseAdmin();
  if (!admin) {
    return NextResponse.json({ error: "서버 관리자 키가 없어요(SUPABASE_SERVICE_ROLE_KEY)." }, { status: 503 });
  }

  // 0) 만료 임박 토큰 갱신 스윕. 실패해도 발행은 계속 진행한다.
  let refresh = { checked: 0, refreshed: 0, failed: 0 };
  try {
    refresh = await refreshExpiringTokens(admin);
  } catch (e) {
    console.error("[api/threads/cron] 토큰 갱신 스윕 실패:", e);
  }

  // 0b) 중단되어 'publishing' 으로 멈춘 글 정리(실패 처리). 다음 실행에서 사용자가 재시도.
  let staleFailed = 0;
  try {
    const staleBefore = new Date(Date.now() - THREADS_PUBLISHING_STALE_MIN * 60 * 1000).toISOString();
    staleFailed = await requeueStalePublishing(admin, staleBefore);
  } catch (e) {
    console.error("[api/threads/cron] 중단 글 정리 실패:", e);
  }

  const nowIso = new Date().toISOString();
  const since24h = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  let published = 0;
  let failed = 0;
  let skipped = 0;

  try {
    const due = await getDuePosts(admin, nowIso, THREADS_CRON_BATCH);
    // 이번 실행 동안 계정별 발행량을 누적 추적(한도 초과 방지).
    const usedByAccount = new Map<string, number>();

    for (const post of due) {
      const account = post.account;
      if (!account) {
        await markFailed(admin, post.id, "연결된 계정 정보를 찾을 수 없어요.");
        failed++;
        continue;
      }

      // 일일 안전 한도 체크(DB 기준 + 이번 배치 누적).
      let used = usedByAccount.get(account.id);
      if (used === undefined) {
        used = await countPublishedSince(admin, account.id, since24h);
        usedByAccount.set(account.id, used);
      }
      if (used >= THREADS_DAILY_CAP) {
        skipped++; // 한도 도달 → 예약 유지, 다음 실행에서 재시도
        continue;
      }

      // 원자적 클레임으로 중복 발행 방지.
      const claimed = await claimForPublish(admin, post.id);
      if (!claimed) {
        skipped++;
        continue;
      }

      try {
        const mediaId = await publishOne({
          threadsUserId: account.threads_user_id,
          accessToken: account.access_token,
          text: post.text,
          mediaType: post.media_type,
          imageUrl: post.image_url,
        });
        await markPublished(admin, post.id, mediaId);
        usedByAccount.set(account.id, used + 1);
        published++;
      } catch (pubErr) {
        const msg = pubErr instanceof Error ? pubErr.message : String(pubErr);
        await markFailed(admin, post.id, msg);
        failed++;
      }
    }

    return NextResponse.json({
      ok: true,
      processed: due.length,
      published,
      failed,
      skipped,
      staleFailed,
      tokensRefreshed: refresh.refreshed,
      tokensRefreshFailed: refresh.failed,
    });
  } catch (err) {
    console.error("[api/threads/cron] 실패:", err);
    return NextResponse.json({ error: "크론 처리 중 문제가 발생했어요." }, { status: 500 });
  }
}
