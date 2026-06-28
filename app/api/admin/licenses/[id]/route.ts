// app/api/admin/licenses/[id]/route.ts  [신규]
//   PATCH  → 상태/속성 변경. body.action: "revoke" | "activate" | "reset-devices"
//            또는 속성 패치 { label?, note?, maxDevices?, expiresAt? }
//   DELETE → 코드 영구 삭제(연결된 기기/로그 cascade)
// 관리자(로그인 + 허용목록) 전용.

import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/license/admin";
import { deleteLicense, resetDevices, setLicenseStatus, updateLicense } from "@/lib/license/db";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, ctx: Ctx) {
  const gate = await requireAdmin();
  if (!gate.ok) return NextResponse.json({ error: gate.error }, { status: gate.status });
  const { id } = await ctx.params;

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  try {
    const action = typeof body.action === "string" ? body.action : "";

    if (action === "revoke" || action === "activate") {
      const license = await setLicenseStatus(gate.admin, id, action === "revoke" ? "revoked" : "active");
      if (!license) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
      return NextResponse.json({ license });
    }

    if (action === "reset-devices") {
      const removed = await resetDevices(gate.admin, id);
      return NextResponse.json({ ok: true, removed });
    }

    // 속성 패치
    const license = await updateLicense(gate.admin, id, {
      label: typeof body.label === "string" ? body.label : undefined,
      note: typeof body.note === "string" ? body.note : undefined,
      maxDevices: typeof body.maxDevices === "number" ? body.maxDevices : undefined,
      expiresAt:
        typeof body.expiresAt === "string"
          ? body.expiresAt
          : body.expiresAt === null
            ? null
            : undefined,
    });
    if (!license) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    return NextResponse.json({ license });
  } catch (err) {
    console.error("[api/admin/licenses/:id] PATCH 실패:", err);
    return NextResponse.json({ error: "변경에 실패했습니다." }, { status: 500 });
  }
}

export async function DELETE(_req: Request, ctx: Ctx) {
  const gate = await requireAdmin();
  if (!gate.ok) return NextResponse.json({ error: gate.error }, { status: gate.status });
  const { id } = await ctx.params;
  try {
    await deleteLicense(gate.admin, id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/admin/licenses/:id] DELETE 실패:", err);
    return NextResponse.json({ error: "삭제에 실패했습니다." }, { status: 500 });
  }
}
