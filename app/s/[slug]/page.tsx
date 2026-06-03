// app/s/[slug]/page.tsx  [신규] — ★공개 게시 페이지(멀티테넌트).
// slug 로 게시된 프로젝트를 조회해 템플릿 + 이메일 신청 폼을 서빙한다.

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { selectPublishedBySlug } from "@/lib/db/projects";
import TemplateRenderer from "@/components/templates/TemplateRenderer";
import LeadForm from "@/components/LeadForm";
import { buildPageMetadata } from "@/lib/seo/meta";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  if (!isSupabaseConfigured()) return { title: "PromptSite" };
  try {
    const supabase = await createSupabaseServer();
    const project = await selectPublishedBySlug(supabase, slug);
    if (project) return buildPageMetadata(project.title, project.copy);
  } catch {
    // 메타 조회 실패는 무시(기본값 사용)
  }
  return { title: "PromptSite" };
}

export default async function PublicPage({ params }: Params) {
  const { slug } = await params;
  if (!isSupabaseConfigured()) notFound();

  const supabase = await createSupabaseServer();
  const project = await selectPublishedBySlug(supabase, slug);
  if (!project) notFound();

  return (
    <div>
      <TemplateRenderer
        templateId={project.template}
        copy={project.copy}
        lang={project.biz_info?.language ?? "ko"}
      />

      {/* 이메일 신청 섹션 — 템플릿 CTA의 #signup 앵커 대상 */}
      <section id="signup" className="bg-slate-900 px-6 py-20 text-center">
        <h2 className="text-2xl font-bold text-white sm:text-3xl">
          {project.copy?.cta?.headline || "지금 신청하세요"}
        </h2>
        <p className="mt-3 text-slate-300">이메일을 남기면 가장 먼저 알려드릴게요.</p>
        <div className="mt-8">
          <LeadForm projectId={project.id} buttonLabel={project.copy?.cta?.button || "신청하기"} />
        </div>
      </section>
    </div>
  );
}
