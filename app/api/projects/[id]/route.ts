// app/api/projects/[id]/route.ts  [신규]
// 단건 프로젝트: GET(불러오기/편집용) · PATCH(재게시·수정) · DELETE(삭제). 모두 소유자만(RLS).
// PATCH 로 게시 상태의 내용(카피·템플릿)이 바뀌거나 게시를 켜면 게시 전 승인을 다시 받는다.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { deleteProject, selectMyProjectById, updateProject, type ProjectPatch } from "@/lib/db/projects";
import { logApproval } from "@/lib/db/complianceLogs";
import { isMyStore } from "@/lib/db/stores";
import { parseApproval, validateApproval } from "@/lib/compliance/approval";
import { parsePlace } from "@/lib/i18n/place";
import { parseTranslations } from "@/lib/i18n/translations";
import type { SectionCopy, TemplateId } from "@/lib/ai/types";

export const runtime = "nodejs";

const VALID_TEMPLATES: TemplateId[] = ["saas-launch", "waitlist", "agency"];

type Ctx = { params: Promise<{ id: string }> };

async function getAuthed() {
  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return { supabase, user };
}

export async function GET(_req: Request, ctx: Ctx) {
  if (!isSupabaseConfigured()) return NextResponse.json({ error: "미설정" }, { status: 503 });
  const { id } = await ctx.params;
  const { supabase, user } = await getAuthed();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  try {
    const project = await selectMyProjectById(supabase, id, user.id);
    if (!project) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    return NextResponse.json({ project });
  } catch (err) {
    console.error("[api/projects/:id] GET 실패:", err);
    return NextResponse.json({ error: "불러오기에 실패했어요." }, { status: 500 });
  }
}

export async function PATCH(req: Request, ctx: Ctx) {
  if (!isSupabaseConfigured()) return NextResponse.json({ error: "미설정" }, { status: 503 });
  const { id } = await ctx.params;
  const { supabase, user } = await getAuthed();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  const patch: ProjectPatch = {};
  if (VALID_TEMPLATES.includes(body.template as TemplateId)) patch.template = body.template as TemplateId;
  if (body.copy && typeof body.copy === "object") patch.copy = body.copy as SectionCopy;
  if (typeof body.published === "boolean") patch.published = body.published;
  if (typeof body.title === "string") patch.title = body.title;
  if (body.place !== undefined) patch.place = parsePlace(body.place);
  if (body.translations !== undefined) patch.translations = parseTranslations(body.translations);
  // 매장 지정(내 매장 id) 또는 해제(null). 내용이 바뀌지 않으므로 게시 승인은 필요 없다.
  if (body.store_id === null) patch.store_id = null;
  else if (typeof body.store_id === "string") {
    if (!(await isMyStore(supabase, body.store_id, user.id))) {
      return NextResponse.json({ error: "매장을 찾을 수 없어요." }, { status: 400 });
    }
    patch.store_id = body.store_id;
  }

  try {
    const current = await selectMyProjectById(supabase, id, user.id);
    if (!current) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });

    const willBePublished = patch.published ?? current.published;
    // 매장 정보·번역본도 공개 페이지에 보이는 내용이라 바뀌면 게시 승인을 다시 받는다
    const contentChanged =
      patch.copy !== undefined || patch.template !== undefined || patch.place !== undefined || patch.translations !== undefined;
    if (willBePublished && (contentChanged || patch.published === true || body.compliance !== undefined)) {
      const approval = validateApproval(patch.copy ?? current.copy, parseApproval(body.compliance));
      if (!approval.ok) {
        return NextResponse.json(
          { error: approval.error, findings: approval.findings, missing: approval.missing },
          { status: 422 },
        );
      }
      patch.compliance = { ...approval.record, approved_by: user.id };
    }

    const project = await updateProject(supabase, id, user.id, patch);
    if (!project) return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
    if (patch.compliance) {
      await logApproval(supabase, {
        projectId: project.id,
        owner: user.id,
        record: patch.compliance,
        template: project.template,
        copy: project.copy,
      });
    }
    return NextResponse.json({ id: project.id, slug: project.slug });
  } catch (err) {
    console.error("[api/projects/:id] PATCH 실패:", err);
    return NextResponse.json({ error: "저장에 실패했어요." }, { status: 500 });
  }
}

export async function DELETE(_req: Request, ctx: Ctx) {
  if (!isSupabaseConfigured()) return NextResponse.json({ error: "미설정" }, { status: 503 });
  const { id } = await ctx.params;
  const { supabase, user } = await getAuthed();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  try {
    await deleteProject(supabase, id, user.id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/projects/:id] DELETE 실패:", err);
    return NextResponse.json({ error: "삭제에 실패했어요." }, { status: 500 });
  }
}
