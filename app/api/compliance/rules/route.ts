// app/api/compliance/rules/route.ts  [신규 — 컴플라이언스 P1 규제 피드]
// GET: 금칙어 규칙·업종 프리셋·AI 고지 문구(JSON). 인증 없음(공개 정보), 1시간 캐시.
// 클라이언트는 version 을 저장해 두고 If-None-Match 로 물어보면 바뀌지 않았을 때 304 를 받는다.

import { buildRulesFeed } from "@/lib/compliance/feed";

const CACHE_HEADERS = {
  "Cache-Control": "public, max-age=3600, s-maxage=3600",
  "Access-Control-Allow-Origin": "*",
};

export async function GET(req: Request) {
  const feed = buildRulesFeed();
  const etag = `"${feed.version}"`;
  if (req.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { ...CACHE_HEADERS, ETag: etag } });
  }
  return Response.json(feed, { headers: { ...CACHE_HEADERS, ETag: etag } });
}
