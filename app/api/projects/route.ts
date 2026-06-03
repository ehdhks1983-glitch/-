// app/api/projects/route.ts  [신규]
// 생성 결과를 projects 에 저장(+게시). 로그인 필요. IP 기준 rate limit.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { insertProject } from "@/lib/db/projects";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";
import type { BizInfo, SectionCopy, TemplateId } from "@/lib/ai/types";

export const runtime = "nodejs";

const PROJECTS_LIMIT = 30; // 분당 저장 횟수(IP 기준)
const PROJECTS_WINDOW_MS = 60_000;
const VALID_TEMPLATES: TemplateId[] = ["saas-launch", "waitlist", "agency"];

export async function POST(req: Request) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "게시 기능이 아직 설정되지 않았어요." }, { status: 503 });
  }

  sweep();
  const rl = rateLimit(clientKey(req, "projects"), PROJECTS_LIMIT, PROJECTS_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json({ error: "잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  const template = VALID_TEMPLATES.includes(body.template as TemplateId)
    ? (body.template as TemplateId)
    : "saas-launch";
  const biz = body.biz_info as BizInfo | undefined;
  const copy = body.copy as SectionCopy | undefined;
  if (!biz || typeof biz !== "object" || !copy || typeof copy !== "object" || !copy.hero) {
    return NextResponse.json({ error: "생성된 페이지 정보가 올바르지 않습니다." }, { status: 400 });
  }

  try {
    const project = await insertProject(supabase, user.id, {
      title: typeof body.title === "string" ? body.title : "",
      prompt: typeof body.prompt === "string" ? body.prompt : "",
      template,
      biz_info: biz,
      copy,
      publish: true,
    });
    return NextResponse.json({ id: project.id, slug: project.slug });
  } catch (err) {
    console.error("[api/projects] 저장 실패:", err);
    return NextResponse.json(
      { error: "저장에 실패했어요. 잠시 후 다시 시도해 주세요." },
      { status: 500 },
    );
  }
}
