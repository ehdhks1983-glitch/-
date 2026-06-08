// scripts/threads-test/01-client.ts
// 가상 테스트 1 — Threads API 클라이언트(lib/threads/client). 실제 네트워크 없이 fetch를 목으로 대체해
// 엔드포인트/파라미터/응답 파싱/에러 처리를 검증한다.
// 실행: npx tsx scripts/threads-test/01-client.ts

import { ok, eq, contains, summary } from "./_assert";
import { installMockFetch, calls, queueResponse } from "./_mockfetch";

// config는 모듈 로드 시 env를 읽으므로 client import 전에 설정해야 한다.
process.env.THREADS_APP_ID = "APPID";
process.env.THREADS_APP_SECRET = "SECRET";
process.env.THREADS_REDIRECT_URI = "https://app.example/api/threads/callback";

const HOST = "https://graph.threads.net";
const last = () => calls[calls.length - 1];

async function main() {
  installMockFetch();
  const c = await import("../../lib/threads/client");

  console.log("STEP 1 — lib/threads/client.ts (가상 테스트)\n");

  // 1) 인가코드 → 단기토큰(+user_id)
  queueResponse({ access_token: "short-tok", user_id: "12345" });
  const short = await c.exchangeCodeForToken("AUTH_CODE");
  eq("short.accessToken", short.accessToken, "short-tok");
  eq("short.userId", short.userId, "12345");
  eq("exchange url", last().url, `${HOST}/oauth/access_token`);
  eq("exchange method", last().method, "POST");
  contains("exchange body: grant_type=authorization_code", last().body, "grant_type=authorization_code");
  contains("exchange body: code", last().body, "code=AUTH_CODE");
  contains("exchange body: client_id", last().body, "client_id=APPID");
  contains("exchange body: client_secret", last().body, "client_secret=SECRET");
  contains(
    "exchange body: redirect_uri(encoded)",
    last().body,
    "redirect_uri=https%3A%2F%2Fapp.example%2Fapi%2Fthreads%2Fcallback",
  );

  // 2) 단기 → 장기 토큰
  queueResponse({ access_token: "long-tok", token_type: "bearer", expires_in: 5183944 });
  const long = await c.exchangeForLongLivedToken("short-tok");
  eq("long.accessToken", long.accessToken, "long-tok");
  eq("long.expiresInSec", long.expiresInSec, 5183944);
  contains("longlived url", last().url, `${HOST}/access_token?`);
  contains("longlived grant", last().url, "grant_type=th_exchange_token");
  contains("longlived secret", last().url, "client_secret=SECRET");
  contains("longlived token", last().url, "access_token=short-tok");
  eq("longlived method", last().method, "GET");

  // 3) 프로필
  queueResponse({ id: "12345", username: "myhandle" });
  const prof = await c.getProfile("12345", "long-tok");
  eq("profile.id", prof.id, "12345");
  eq("profile.username", prof.username, "myhandle");
  contains("profile url", last().url, `${HOST}/12345?`);
  contains("profile fields", last().url, "fields=id%2Cusername");
  contains("profile token", last().url, "access_token=long-tok");

  // 4) 컨테이너 생성(TEXT)
  queueResponse({ id: "CREATION_1" });
  const creation = await c.createContainer("12345", "long-tok", { mediaType: "TEXT", text: "안녕하세요 글" });
  eq("creation id", creation, "CREATION_1");
  eq("create url", last().url, `${HOST}/12345/threads`);
  eq("create method", last().method, "POST");
  contains("create media_type=TEXT", last().body, "media_type=TEXT");
  contains("create text present", last().body, "text=");
  contains("create token", last().body, "access_token=long-tok");

  // 5) 발행
  queueResponse({ id: "MEDIA_1" });
  const media = await c.publishContainer("12345", "long-tok", "CREATION_1");
  eq("publish media id", media, "MEDIA_1");
  eq("publish url", last().url, `${HOST}/12345/threads_publish`);
  contains("publish creation_id", last().body, "creation_id=CREATION_1");

  // 6) 발행 한도 파싱
  queueResponse({ data: [{ quota_usage: 7, config: { quota_total: 250 } }] });
  const usage = await c.getPublishingUsage("12345", "long-tok");
  eq("usage.used", usage.used, 7);
  eq("usage.total", usage.total, 250);

  // 7) 에러 응답 → throw (Meta 메시지 추출 + 접두사)
  queueResponse({ error: { message: "Invalid OAuth access token" } }, 400);
  let threw = "";
  try {
    await c.getProfile("12345", "bad");
  } catch (e) {
    threw = e instanceof Error ? e.message : String(e);
  }
  contains("error: Meta 메시지 노출", threw, "Invalid OAuth access token");
  ok("error: 접두사 'Threads API 오류:'", threw.startsWith("Threads API 오류:"));

  // 8) IMAGE 컨테이너는 image_url 포함
  queueResponse({ id: "CRE_IMG" });
  await c.createContainer("12345", "long-tok", {
    mediaType: "IMAGE",
    text: "cap",
    imageUrl: "https://img.example/a.jpg",
  });
  contains("image media_type=IMAGE", last().body, "media_type=IMAGE");
  contains("image url(encoded)", last().body, "image_url=https%3A%2F%2Fimg.example%2Fa.jpg");

  // 9) 빈 id 응답 → 명확한 에러
  queueResponse({});
  let noId = "";
  try {
    await c.publishContainer("12345", "long-tok", "X");
  } catch (e) {
    noId = e instanceof Error ? e.message : String(e);
  }
  contains("publish: id 없으면 에러", noId, "id가 없습니다");

  summary("STEP 1 — client.ts");
}

main().catch((err) => {
  console.error("❌ 테스트 실행 오류:", err);
  process.exit(1);
});
