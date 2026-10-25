// app/api/approve/[token]/route.ts  [신규 — P2 대행사 모드]
// 사장님이 승인 링크에서 '승인하고 게시'를 누르면 호출(로그인 없음 — 링크 토큰이 권한).
// 서버가 스냅샷을 금칙어·필수 표시 규칙으로 다시 검사한 뒤에만 게시하고, 승인자 이름과 경로를 기록한다.

import { NextResponse } from "next/server";
import { createSupabaseAdmin } from "@/lib/db/supabase-server";
import { updateProject } from "@/lib/db/projects";
import { isExpired, markRequestApproved, selectRequestByToken } from "@/lib/db/approvalRequests";
import { logApproval } from "@/lib/db/complianceLogs";
import { parseApproval, validateApproval } from "@/lib/compliance/approval";
import { sanitizeText } from "@/lib/sanitize";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

export async function POST(req: Request, ctx: { params: Promise<{ token: string }> }) {
  const admin = createSupabaseAdmin();
  if (!admin) return NextResponse.json({ error: "승인 링크 기능이 아직 설정되지 않았어요." }, { status: 503 });
  sweep();
  if (!rateLimit(clientKey(req, "approve"), 10, 60_000).ok) {
    return NextResponse.json({ error: "잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  const { token } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const name = sanitizeText(body.name, 40);
  if (!name) return NextResponse.json({ error: "승인하시는 분의 이름을 적어 주세요." }, { status: 400 });
  if (body.approved !== true) return NextResponse.json({ error: "내용을 확인하고 승인에 체크해 주세요." }, { status: 400 });

  try {
    const request = await selectRequestByToken(admin, token);
    if (!request || request.status === "cancelled") {
      return NextResponse.json({ error: "더 이상 유효하지 않은 링크예요. 담당자에게 새 링크를 요청해 주세요." }, { status: 404 });
    }
    if (request.status === "approved") return NextResponse.json({ error: "이미 승인된 요청이에요." }, { status: 409 });
    if (isExpired(request)) return NextResponse.json({ error: "링크 유효기간이 지났어요. 담당자에게 새 링크를 요청해 주세요." }, { status: 410 });

    const check = validateApproval(request.copy, parseApproval({ ...request.draft, approved: true }));
    if (!check.ok) return NextResponse.json({ error: check.error, findings: check.findings }, { status: 422 });

    // 상태를 먼저 '승인'으로 바꿔 동시 승인을 막는다
    if (!(await markRequestApproved(admin, request.id, name))) {
      return NextResponse.json({ error: "이미 처리된 요청이에요." }, { status: 409 });
    }
    const record = { ...check.record, approved_by: request.owner, approved_via: "client_link" as const, approver_name: name };
    const project = await updateProject(admin, request.project_id, request.owner, {
      template: request.template,
      copy: request.copy,
      published: true,
      compliance: record,
    });
    if (!project) {
      await admin.from("approval_requests").update({ status: "pending", approved_at: null, approver_name: null }).eq("id", request.id);
      return NextResponse.json({ error: "페이지를 찾을 수 없어요." }, { status: 404 });
    }
    await logApproval(admin, { projectId: project.id, owner: request.owner, record, template: request.template, copy: request.copy });
    return NextResponse.json({ url: `${new URL(req.url).origin}/s/${project.slug}` });
  } catch (err) {
    console.error("[api/approve] 실패:", err);
    return NextResponse.json({ error: "승인 처리에 실패했어요. 잠시 후 다시 시도해 주세요." }, { status: 500 });
  }
}
