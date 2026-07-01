// app/api/status/route.ts
// 클라이언트가 신청 접수 가능 여부를 알 수 있게 한다(Supabase 설정 여부).
// → 신청 폼에서 "접수 비활성" 안내 배너를 띄우는 용도.

import { NextResponse } from "next/server";
import { isSupabaseConfigured } from "@/lib/db/supabase";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({
    submissionsEnabled: isSupabaseConfigured(),
  });
}
