// scripts/threads-test/07-image.ts
// 가상 테스트 8 — 이미지 발행 폴링(lib/threads/publish). 실제 네트워크 없이 fetch 목 + 주입 sleep 으로:
//   - TEXT: status 폴링 없이 즉시 발행
//   - IMAGE: FINISHED 될 때까지 폴링 후 발행 (IN_PROGRESS → 대기 → FINISHED)
//   - ERROR/타임아웃: 발행하지 않고 throw
// 실행: npx tsx scripts/threads-test/07-image.ts

import { ok, eq, contains, summary } from "./_assert";
import { installMockFetch, calls, queueResponse } from "./_mockfetch";

process.env.THREADS_APP_ID = "APPID";
process.env.THREADS_APP_SECRET = "SECRET";
process.env.THREADS_REDIRECT_URI = "https://app.example/api/threads/callback";
// 타임아웃 테스트를 빠르게: 최대 폴링 3회.
process.env.THREADS_MEDIA_POLL_ATTEMPTS = "3";

const isStatus = (u: string) => u.includes("fields=status");
const isPublish = (u: string) => u.includes("/threads_publish");

async function main() {
  const { publishOne } = await import("../../lib/threads/publish");
  console.log("STEP 8 — lib/threads/publish.ts 이미지 폴링 (가상 테스트)\n");

  let sleeps = 0;
  const sleep = async () => {
    sleeps++;
  };
  const IMG = { threadsUserId: "12345", accessToken: "t", text: "cap", mediaType: "IMAGE" as const, imageUrl: "https://i/x.jpg" };

  // 1) TEXT: 폴링 없이 즉시 발행
  installMockFetch();
  sleeps = 0;
  queueResponse({ id: "C" });
  queueResponse({ id: "M" });
  const mText = await publishOne({ threadsUserId: "12345", accessToken: "t", text: "hi", mediaType: "TEXT" }, { sleep });
  eq("TEXT: 미디어 id", mText, "M");
  eq("TEXT: 호출 2회(생성+발행)", calls.length, 2);
  ok("TEXT: status 폴링 없음", calls.every((c) => !isStatus(c.url)));
  eq("TEXT: sleep 0", sleeps, 0);

  // 2) IMAGE: 즉시 FINISHED
  installMockFetch();
  sleeps = 0;
  queueResponse({ id: "C" });
  queueResponse({ status: "FINISHED" });
  queueResponse({ id: "M" });
  const mImg = await publishOne(IMG, { sleep });
  eq("IMAGE: 미디어 id", mImg, "M");
  eq("IMAGE finished: status 1회", calls.filter((c) => isStatus(c.url)).length, 1);
  eq("IMAGE finished: sleep 0", sleeps, 0);
  ok("IMAGE finished: 마지막 발행 호출", isPublish(calls[calls.length - 1].url));

  // 3) IMAGE: IN_PROGRESS → 대기 → FINISHED
  installMockFetch();
  sleeps = 0;
  queueResponse({ id: "C" });
  queueResponse({ status: "IN_PROGRESS" });
  queueResponse({ status: "FINISHED" });
  queueResponse({ id: "M" });
  const mImg2 = await publishOne(IMG, { sleep });
  eq("IMAGE progress: 미디어 id", mImg2, "M");
  eq("IMAGE progress: status 2회", calls.filter((c) => isStatus(c.url)).length, 2);
  eq("IMAGE progress: sleep 1회", sleeps, 1);
  ok("IMAGE progress: 발행됨", calls.some((c) => isPublish(c.url)));

  // 4) IMAGE: ERROR → 발행 안 함, 메시지 전파
  installMockFetch();
  sleeps = 0;
  queueResponse({ id: "C" });
  queueResponse({ status: "ERROR", error_message: "bad image" });
  let e1 = "";
  try {
    await publishOne(IMG, { sleep });
  } catch (e) {
    e1 = e instanceof Error ? e.message : String(e);
  }
  contains("ERROR: '미디어 처리 실패'", e1, "미디어 처리 실패");
  contains("ERROR: 원인 메시지 포함", e1, "bad image");
  ok("ERROR: 발행 호출 안 함", calls.every((c) => !isPublish(c.url)));

  // 5) IMAGE: 타임아웃(계속 IN_PROGRESS) → throw, 발행 안 함
  installMockFetch();
  sleeps = 0;
  queueResponse({ id: "C" });
  queueResponse({ status: "IN_PROGRESS" });
  queueResponse({ status: "IN_PROGRESS" });
  queueResponse({ status: "IN_PROGRESS" });
  let e2 = "";
  try {
    await publishOne(IMG, { sleep });
  } catch (e) {
    e2 = e instanceof Error ? e.message : String(e);
  }
  contains("timeout: 시간 초과 메시지", e2, "시간이 초과");
  eq("timeout: status 정확히 3회(attempts)", calls.filter((c) => isStatus(c.url)).length, 3);
  eq("timeout: sleep 3회", sleeps, 3);
  ok("timeout: 발행 호출 안 함", calls.every((c) => !isPublish(c.url)));

  summary("STEP 8 — publish.ts 이미지 폴링");
}

main().catch((err) => {
  console.error("❌ 테스트 실행 오류:", err);
  process.exit(1);
});
