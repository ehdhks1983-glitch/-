// app/api/admin/licenses/route.ts  [신규]
//   GET  → 라이선스 목록(+ 기기 사용량)
//   POST → 새 코드 발급  { label?, note?, maxDevices?, validDays?|expiresAt? }
// 모두 관리자(로그인 + 허용목록) 전용. 실제 DB 접근은 service_role.

import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/license/admin";
import { createLicense, listLicenses } from "@/lib/license/db";

export const runtime = "nodejs";

export async function GET() {
  const gate = await requireAdmin();
  if (!gate.ok) return NextResponse.json({ error: gate.error }, { status: gate.status });
  try {
    const licenses = await listLicenses(gate.admin);
    return NextResponse.json({ licenses });
  } catch (err) {
    console.error("[api/admin/licenses] GET 실패:", err);
    return NextResponse.json({ error: "목록을 불러오지 못했습니다." }, { status: 500 });
  }
}

export async function POST(req: Request) {
  const gate = await requireAdmin();
  if (!gate.ok) return NextResponse.json({ error: gate.error }, { status: gate.status });

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  const label = typeof body.label === "string" ? body.label : "";
  const note = typeof body.note === "string" ? body.note : "";
  const maxDevices = typeof body.maxDevices === "number" ? body.maxDevices : 1;
  const validDays =
    typeof body.validDays === "number" ? body.validDays : body.validDays === null ? null : undefined;
  const expiresAt = typeof body.expiresAt === "string" ? body.expiresAt : undefined;

  try {
    const license = await createLicense(gate.admin, { label, note, maxDevices, validDays, expiresAt });
    return NextResponse.json({ license }, { status: 201 });
  } catch (err) {
    console.error("[api/admin/licenses] POST 실패:", err);
    return NextResponse.json({ error: "코드 발급에 실패했습니다." }, { status: 500 });
  }
}
