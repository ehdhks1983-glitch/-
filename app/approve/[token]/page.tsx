// app/approve/[token]/page.tsx  [신규 — P2 대행사 모드]
// 사장님용 승인 페이지(로그인 없음 — 링크 토큰이 권한). 대행사가 보낸 내용의 미리보기와
// 광고 문구 검사 결과를 보여 주고, 승인하면 게시된다. 검색엔진 색인 제외.

import type { Metadata } from "next";
import { createSupabaseAdmin } from "@/lib/db/supabase-server";
import { isExpired, selectRequestByToken, type ApprovalRequestRow } from "@/lib/db/approvalRequests";
import { checkCopy, hasBlocking } from "@/lib/compliance/check";
import { getIndustry } from "@/lib/compliance/industries";
import { sanitizeCopy } from "@/lib/sanitize";
import TemplateRenderer from "@/components/templates/TemplateRenderer";
import ComplianceFooter from "@/components/ComplianceFooter";
import ClientApproveForm from "@/components/ClientApproveForm";
import PlaceSection from "@/components/PlaceSection";
import { FOREIGN_LANGS, LANG_NAMES } from "@/lib/i18n/langs";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "게시 승인 요청", robots: { index: false, follow: false } };

export default async function ApprovePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const admin = createSupabaseAdmin();
  if (!admin) return <Notice title="승인 링크 기능이 아직 설정되지 않았어요" body="담당자에게 문의해 주세요." />;

  let request: ApprovalRequestRow | null = null;
  let biz = null;
  try {
    request = await selectRequestByToken(admin, token);
    if (request) {
      const { data } = await admin.from("projects").select("biz_info").eq("id", request.project_id).maybeSingle();
      biz = data?.biz_info ?? null;
    }
  } catch (err) {
    console.error("[approve] 조회 실패:", err);
  }

  if (!request || request.status === "cancelled") {
    return <Notice title="유효하지 않은 링크예요" body="더 최신 내용으로 다시 요청됐거나 취소된 링크일 수 있어요. 담당자에게 새 링크를 요청해 주세요." />;
  }
  if (request.status === "approved") {
    return <Notice title="이미 승인된 요청이에요" body={`${request.approver_name ?? ""}님이 승인했어요. 감사합니다.`} />;
  }
  if (isExpired(request)) {
    return <Notice title="링크 유효기간이 지났어요" body="담당자에게 새 링크를 요청해 주세요." />;
  }

  const industry = request.draft.industry;
  const findings = checkCopy(sanitizeCopy(request.copy), industry);
  const blocked = hasBlocking(findings);
  const lang = biz?.language ?? "ko";
  const translated = FOREIGN_LANGS.filter((l) => request.draft.translations?.[l]);

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-3xl px-5 py-8">
        <h1 className="text-2xl font-bold">페이지 게시 승인 요청</h1>
        <p className="mt-1 text-sm text-slate-500">
          담당자가 만든 홍보 페이지예요. 내용을 확인하고 승인하면 바로 게시됩니다. 업종: {getIndustry(industry).name} · 유효기간{" "}
          {new Date(request.expires_at).toLocaleDateString("ko-KR")}까지
        </p>

        <section className="mt-5 rounded-xl border border-slate-200 bg-white p-5 text-sm">
          <h2 className="font-semibold">광고 문구 검사</h2>
          {findings.length === 0 ? (
            <p className="mt-2 text-emerald-700">문제 될 만한 표현을 찾지 못했어요.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {findings.map((f, i) => (
                <li
                  key={`${f.ruleId}-${i}`}
                  className={f.severity === "block" ? "rounded-lg bg-red-50 px-3 py-2 text-red-800" : "rounded-lg bg-amber-50 px-3 py-2 text-amber-900"}
                >
                  <span className="font-semibold">{f.severity === "block" ? "게시 불가" : "확인 필요"}</span> · {f.fieldLabel} · “{f.match}” —{" "}
                  {f.message}
                </li>
              ))}
            </ul>
          )}
          {blocked && <p className="mt-3 font-medium text-red-700">게시할 수 없는 표현이 있어요. 담당자에게 수정을 요청해 주세요.</p>}
        </section>

        {translated.length > 0 && (
          <p className="mt-3 text-sm text-slate-500">
            외국인 손님용 번역본도 함께 게시돼요: {translated.map((l) => LANG_NAMES[l]).join(", ")} (원문과 같은 뜻으로만 번역)
          </p>
        )}

        <div className="mt-5">
          <ClientApproveForm token={token} disabled={blocked} />
        </div>

        <h2 className="mt-8 text-sm font-semibold text-slate-500">페이지 미리보기</h2>
        <div className="mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <TemplateRenderer templateId={request.template} copy={request.copy} lang={lang} biz={biz} />
          <PlaceSection place={request.draft.place ?? {}} lang={lang} />
          <ComplianceFooter lang={lang} aiLabel={request.draft.ai_label} industry={industry} disclosures={request.draft.disclosures} />
        </div>
      </div>
    </div>
  );
}

function Notice({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
      <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold">{title}</h1>
        <p className="mt-2 text-slate-600">{body}</p>
      </div>
    </div>
  );
}
