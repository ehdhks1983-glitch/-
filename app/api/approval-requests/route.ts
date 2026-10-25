// app/api/approval-requests/route.ts  [신규 — P2 대행사 모드]
// 사장님 승인 요청 링크 만들기(POST). 로그인 필요(대행사·작성자).
// 요청 시점의 카피·템플릿·업종·표시 설정을 스냅샷으로 저장한다 — 게시 중인 페이지는 승인 전까지 바뀌지 않는다.
// 직접 게시와 같은 검사(금칙어 block·필수 표시·AI 표시 확인)를 통과해야 링크를 만들 수 있다.

import { NextResponse } from "next/server";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { insertProject, selectMyProjectById } from "@/lib/db/projects";
import { createApprovalRequest } from "@/lib/db/approvalRequests";
import { parseApproval, validateApproval } from "@/lib/compliance/approval";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";
import { parsePlace } from "@/lib/i18n/place";
import { parseTranslations } from "@/lib/i18n/translations";
import type { BizInfo, SectionCopy, TemplateId } from "@/lib/ai/types";

export const runtime = "nodejs";

const VALID_TEMPLATES: TemplateId[] = ["saas-launch", "waitlist", "agency"];

export async function POST(req: Request) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "승인 요청 기능이 아직 설정되지 않았어요(Supabase 설정 필요)." }, { status: 503 });
  }
  sweep();
  if (!rateLimit(clientKey(req, "approval-requests"), 20, 60_000).ok) {
    return NextResponse.json({ error: "잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  const body = (await req.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });

  const template = VALID_TEMPLATES.includes(body.template as TemplateId) ? (body.template as TemplateId) : "saas-launch";
  const copy = body.copy as SectionCopy | undefined;
  if (!copy || typeof copy !== "object" || !copy.hero) {
    return NextResponse.json({ error: "페이지 내용이 올바르지 않습니다." }, { status: 400 });
  }

  // 사장님 승인 대신 '요청 가능 여부'만 본다: approved 는 링크에서 사장님이 체크한다.
  const approval = parseApproval({ ...(body.draft as Record<string, unknown>), approved: true });
  const check = validateApproval(copy, approval);
  if (!check.ok || !approval) {
    return NextResponse.json(
      { error: check.ok ? "업종을 선택해 주세요." : check.error, findings: check.ok ? undefined : check.findings },
      { status: 422 },
    );
  }

  try {
    let projectId = typeof body.projectId === "string" ? body.projectId : "";
    if (projectId) {
      if (!(await selectMyProjectById(supabase, projectId, user.id))) {
        return NextResponse.json({ error: "찾을 수 없어요." }, { status: 404 });
      }
    } else {
      const biz = body.biz_info as BizInfo | undefined;
      if (!biz || typeof biz !== "object") return NextResponse.json({ error: "페이지 정보가 올바르지 않습니다." }, { status: 400 });
      const project = await insertProject(supabase, user.id, {
        title: typeof body.title === "string" ? body.title : "",
        prompt: typeof body.prompt === "string" ? body.prompt : "",
        template,
        biz_info: biz,
        copy,
        publish: false,
      });
      projectId = project.id;
    }

    const { token, expiresAt } = await createApprovalRequest(supabase, user.id, {
      projectId,
      template,
      copy,
      draft: {
        industry: approval.industry,
        ai_label: approval.ai_label,
        label_off_ack: approval.label_off_ack,
        disclosures: approval.disclosures,
        place: parsePlace(body.place),
        translations: parseTranslations(body.translations),
      },
    });
    return NextResponse.json({ url: `${new URL(req.url).origin}/approve/${token}`, expiresAt, projectId });
  } catch (err) {
    console.error("[api/approval-requests] 실패:", err);
    return NextResponse.json({ error: "승인 요청 링크를 만들지 못했어요." }, { status: 500 });
  }
}
