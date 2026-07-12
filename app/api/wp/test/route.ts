// app/api/wp/test/route.ts  [신규 — 워드프레스 자동 발행]
// 연결 테스트: 주소 정규화 → SSRF 가드 → 인증 확인(users/me) → 사이트 이름 조회.
// 성공 시 정규화된 주소를 돌려줘 클라이언트가 그 값을 저장하게 한다.

import { NextResponse } from "next/server";
import { testConnection } from "@/lib/wp/client";
import { normalizeSiteUrl } from "@/lib/wp/guard";
import { strField, tooMany, badRequest, wpErrorResponse } from "@/lib/wp/serverUtil";
import { WP_CONNECTION_LIMITS } from "@/lib/wp/connection";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const TEST_LIMIT = 20; // 분당 연결 시도(IP 기준) — 비밀번호 무차별 대입 방지
const TEST_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  sweep();
  const rl = rateLimit(clientKey(req, "wp-test"), TEST_LIMIT, TEST_WINDOW_MS);
  if (!rl.ok) return tooMany();

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return badRequest("요청 형식이 올바르지 않습니다.");
  }

  const rawUrl = strField(body, "url", WP_CONNECTION_LIMITS.url);
  const user = strField(body, "user", WP_CONNECTION_LIMITS.user);
  const appPassword = strField(body, "appPassword", WP_CONNECTION_LIMITS.appPassword);

  if (!rawUrl) return badRequest("사이트 주소를 입력해 주세요.");
  if (!user) return badRequest("워드프레스 아이디를 입력해 주세요.");
  if (appPassword.replace(/\s/g, "").length < 8) {
    return badRequest("응용 프로그램 비밀번호를 확인해 주세요. (프로필에서 발급한 24자리)");
  }

  try {
    const url = normalizeSiteUrl(rawUrl);
    const info = await testConnection({ url, user, appPassword });
    return NextResponse.json({
      ok: true,
      connection: { url, user },
      site: { name: info.siteName, url: info.siteUrl },
      wpUser: { name: info.userName },
    });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/test");
  }
}
