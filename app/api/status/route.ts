// app/api/status/route.ts  [신규]
// 클라이언트가 현재 동작 상태를 알 수 있게 한다: 목(mock) 모드 여부 + Supabase 설정 여부.
// → 입력 화면에서 "데모 모드"/"게시 비활성" 안내 배너를 띄우는 용도.

import { NextResponse } from "next/server";
import { isMockMode } from "@/lib/ai/core";
import { isSupabaseConfigured } from "@/lib/db/supabase";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({
    mock: isMockMode(),
    supabaseConfigured: isSupabaseConfigured(),
  });
}
