// app/api/license/verify/route.ts  [신규]
// 봇이 호출하는 공개 온라인 검증 엔드포인트.
//   POST { code, device_id, bot_id?, device_label? }
// 비즈니스 결과(유효/무효)는 항상 HTTP 200 + { valid, reason, ... } 로 응답한다
// (봇 클라이언트가 JSON 파싱 한 번으로 분기하도록). 잘못된 요청/한도 초과/미설정/오류만 4xx·5xx.

import { NextResponse } from "next/server";
import { createSupabaseAdmin } from "@/lib/db/supabase-server";
import { verifyLicense } from "@/lib/license/db";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const VERIFY_LIMIT = 60; // IP당 분당 검증 횟수
const VERIFY_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  const admin = createSupabaseAdmin();
  if (!admin) {
    return NextResponse.json(
      { valid: false, reason: "unconfigured", message: "라이선스 시스템이 설정되지 않았습니다." },
      { status: 503 },
    );
  }

  sweep();
  const rl = rateLimit(clientKey(req, "license-verify"), VERIFY_LIMIT, VERIFY_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json(
      { valid: false, reason: "rate_limited", message: "잠시 후 다시 시도해 주세요." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSec) } },
    );
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { valid: false, reason: "bad_request", message: "잘못된 요청입니다." },
      { status: 400 },
    );
  }

  // device_id/deviceId, bot_id/botId 양쪽 표기 모두 허용.
  const code = typeof body.code === "string" ? body.code : "";
  const deviceId =
    typeof body.device_id === "string"
      ? body.device_id
      : typeof body.deviceId === "string"
        ? body.deviceId
        : "";
  const botId =
    typeof body.bot_id === "string" ? body.bot_id : typeof body.botId === "string" ? body.botId : "";
  const deviceLabel =
    typeof body.device_label === "string"
      ? body.device_label
      : typeof body.deviceLabel === "string"
        ? body.deviceLabel
        : "";

  if (!code.trim()) {
    return NextResponse.json(
      { valid: false, reason: "bad_request", message: "코드가 필요합니다." },
      { status: 400 },
    );
  }

  try {
    const r = await verifyLicense(admin, { code, deviceId, botId, deviceLabel });
    return NextResponse.json(
      { valid: r.valid, reason: r.reason, message: r.message, license: r.license ?? null },
      { status: 200 },
    );
  } catch (err) {
    console.error("[api/license/verify] 실패:", err);
    return NextResponse.json(
      { valid: false, reason: "server_error", message: "검증 중 오류가 발생했습니다." },
      { status: 500 },
    );
  }
}
