// app/api/generations/[id]/route.ts — GET 상태 + 결과 조회(폴링, 스펙 §11). 본인 리소스만.

import { NextResponse } from "next/server";
import { currentOwner } from "@/lib/auth";
import { toClientGeneration } from "@/lib/multipublish/serialize";
import { requestStore } from "@/lib/store";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const { owner, configured } = await currentOwner();
  if (configured && !owner) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  try {
    const store = await requestStore();
    const rec = await store.getById(id, owner ?? undefined);
    if (!rec) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    return NextResponse.json({ generation: toClientGeneration(rec) });
  } catch (err) {
    console.error("[api/generations/:id] 조회 실패:", err);
    return NextResponse.json({ error: "조회에 실패했어요." }, { status: 500 });
  }
}
