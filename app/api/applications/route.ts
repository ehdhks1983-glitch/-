// app/api/applications/route.ts
// 공개 신청 폼(숙소/크리에이터) 저장. IP 기준 rate limit + 필드 검증 + 정화.
// RLS 정책상 kind 가 host/creator 일 때만 insert 된다.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { insertApplication } from "@/lib/db/applications";
import { configFor, isApplicationKind, isValidEmail } from "@/lib/applications";
import { sanitizeText } from "@/lib/sanitize";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const LIMIT = 8; // 분당 신청 횟수(IP 기준)
const WINDOW_MS = 60_000;

export async function POST(req: Request) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json(
      { error: "신청 접수가 아직 설정되지 않았어요. 잠시 후 다시 시도하거나 이메일로 문의해 주세요." },
      { status: 503 },
    );
  }

  sweep();
  const rl = rateLimit(clientKey(req, "applications"), LIMIT, WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json({ error: "잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  if (!isApplicationKind(body.kind)) {
    return NextResponse.json({ error: "잘못된 신청 유형입니다." }, { status: 400 });
  }
  const config = configFor(body.kind);
  const rawFields = (body.fields ?? {}) as Record<string, unknown>;

  // 설정된 필드만 화이트리스트로 받아 정화한다(임의 키 주입 차단).
  const clean: Record<string, string> = {};
  for (const f of config.fields) {
    const max = f.maxLen ?? 1000;
    if (f.type === "checkboxes") {
      const arr = Array.isArray(rawFields[f.name]) ? (rawFields[f.name] as unknown[]) : [];
      const picked = arr
        .map((v) => sanitizeText(v, 60))
        .filter((v) => f.options?.includes(v));
      clean[f.name] = picked.join(", ");
    } else {
      clean[f.name] = sanitizeText(rawFields[f.name], max);
    }
    if (f.required && !clean[f.name]) {
      return NextResponse.json({ error: `'${f.label}' 항목을 입력해 주세요.` }, { status: 400 });
    }
  }

  const email = clean.email ?? "";
  if (!isValidEmail(email)) {
    return NextResponse.json({ error: "이메일 형식을 확인해 주세요." }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServer();
    await insertApplication(supabase, {
      kind: body.kind,
      name: clean.name || clean.stayName || "",
      email,
      phone: clean.phone || undefined,
      region: clean.region || undefined,
      payload: clean,
    });
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/applications] 실패:", err);
    return NextResponse.json(
      { error: "신청 저장에 실패했어요. 잠시 후 다시 시도해 주세요." },
      { status: 500 },
    );
  }
}
