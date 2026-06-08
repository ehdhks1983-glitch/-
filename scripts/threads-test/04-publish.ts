// scripts/threads-test/04-publish.ts
// 가상 테스트 4 — 발행 로직(lib/threads/publish). createContainer → publishContainer 2단계 순서와
// 미디어 id 반환, 에러 전파를 목 fetch로 검증.
// 실행: npx tsx scripts/threads-test/04-publish.ts

import { ok, eq, contains, summary } from "./_assert";
import { installMockFetch, calls, queueResponse } from "./_mockfetch";

process.env.THREADS_APP_ID = "APPID";
process.env.THREADS_APP_SECRET = "SECRET";
process.env.THREADS_REDIRECT_URI = "https://app.example/api/threads/callback";

async function main() {
  const { publishOne } = await import("../../lib/threads/publish");

  console.log("STEP 4 — lib/threads/publish.ts (가상 테스트)\n");

  // 정상: 생성 → 발행
  installMockFetch();
  queueResponse({ id: "CRE_1" }); // createContainer
  queueResponse({ id: "MEDIA_9" }); // publishContainer
  const mediaId = await publishOne({
    threadsUserId: "12345",
    accessToken: "long-tok",
    text: "오늘의 글",
    mediaType: "TEXT",
  });
  eq("미디어 id 반환", mediaId, "MEDIA_9");
  eq("호출 2회(생성+발행)", calls.length, 2);
  contains("1번째 = 컨테이너 생성", calls[0].url, "/12345/threads");
  ok("1번째는 publish 엔드포인트 아님", calls[0].url.endsWith("/threads"));
  contains("2번째 = 발행", calls[1].url, "/12345/threads_publish");
  contains("발행 body에 creation_id=CRE_1", calls[1].body, "creation_id=CRE_1");

  // 생성 단계 실패 → 발행 호출 안 하고 throw
  installMockFetch();
  queueResponse({ error: { message: "boom at create" } }, 400);
  let err1 = "";
  try {
    await publishOne({ threadsUserId: "1", accessToken: "t", text: "x", mediaType: "TEXT" });
  } catch (e) {
    err1 = e instanceof Error ? e.message : String(e);
  }
  contains("생성 실패 메시지 전파", err1, "boom at create");
  eq("생성 실패 시 발행 호출 안 함(호출 1회)", calls.length, 1);

  // 발행 단계 실패 → throw
  installMockFetch();
  queueResponse({ id: "CRE_2" });
  queueResponse({ error: { message: "boom at publish" } }, 400);
  let err2 = "";
  try {
    await publishOne({ threadsUserId: "1", accessToken: "t", text: "x", mediaType: "TEXT" });
  } catch (e) {
    err2 = e instanceof Error ? e.message : String(e);
  }
  contains("발행 실패 메시지 전파", err2, "boom at publish");
  eq("발행 실패 시 호출 2회", calls.length, 2);

  summary("STEP 4 — publish.ts");
}

main().catch((err) => {
  console.error("❌ 테스트 실행 오류:", err);
  process.exit(1);
});
