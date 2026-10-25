// app/s/[slug]/page.tsx  [신규] — ★공개 게시 페이지(멀티테넌트).
// slug 로 게시된 프로젝트를 조회해 템플릿 + 매장 안내 + 이메일 신청 폼 + 고지 띠(AI 표시·업종 필수 표시)를 서빙한다.
// 외국인 손님용 번역본이 있으면 ?lang=en|ja|zh-CN|zh-TW 로 같은 페이지를 그 언어로 보여 주고(언어 전환 링크·hreflang),
// 매장 정보는 구조화 데이터(JSON-LD)로도 내보낸다.

import type { Metadata } from "next";
import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer } from "@/lib/db/supabase-server";
import { selectPublishedBySlug, type ProjectRow } from "@/lib/db/projects";
import TemplateRenderer from "@/components/templates/TemplateRenderer";
import LeadForm from "@/components/LeadForm";
import ComplianceFooter from "@/components/ComplianceFooter";
import PlaceSection from "@/components/PlaceSection";
import ViewTracker from "@/components/ViewTracker";
import { detectIndustry, isIndustryId } from "@/lib/compliance/industries";
import { buildPageMetadata } from "@/lib/seo/meta";
import { FOREIGN_LANGS, LANG_NAMES, isForeignLang, type PageLang } from "@/lib/i18n/langs";
import { uiText } from "@/lib/i18n/ui";
import { hasPlace, jsonLdString, localBusinessJsonLd } from "@/lib/i18n/place";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ slug: string }>; searchParams: Promise<{ lang?: string }> };

/** 요청 언어의 번역본이 있으면 그 언어, 없으면 원문 언어. */
function pickLang(project: ProjectRow, requested: string | undefined): PageLang {
  if (isForeignLang(requested) && project.translations?.[requested]) return requested;
  return project.biz_info?.language ?? "ko";
}

function copyFor(project: ProjectRow, lang: PageLang) {
  return isForeignLang(lang) && project.translations?.[lang] ? project.translations[lang]!.copy : project.copy;
}

function availableLangs(project: ProjectRow): PageLang[] {
  return [project.biz_info?.language ?? "ko", ...FOREIGN_LANGS.filter((l) => project.translations?.[l])];
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { slug } = await params;
  const { lang: requested } = await searchParams;
  if (!isSupabaseConfigured()) return { title: "PromptSite" };
  try {
    const supabase = await createSupabaseServer();
    const project = await selectPublishedBySlug(supabase, slug);
    if (project) {
      const lang = pickLang(project, requested);
      const langs = availableLangs(project);
      const meta = buildPageMetadata(project.title, copyFor(project, lang));
      if (langs.length > 1) {
        meta.alternates = {
          languages: Object.fromEntries(langs.map((l, i) => [l, i === 0 ? `/s/${slug}` : `/s/${slug}?lang=${l}`])),
        };
      }
      return meta;
    }
  } catch {
    // 메타 조회 실패는 무시(기본값 사용)
  }
  return { title: "PromptSite" };
}

export default async function PublicPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const { lang: requested } = await searchParams;
  if (!isSupabaseConfigured()) notFound();

  const supabase = await createSupabaseServer();
  const project = await selectPublishedBySlug(supabase, slug);
  if (!project) notFound();

  const lang = pickLang(project, requested);
  const copy = copyFor(project, lang);
  const t = uiText(lang).signup;
  const langs = availableLangs(project);
  const place = { name: project.biz_info?.service_name || project.title, ...(project.place ?? {}) };
  const translatedHours = isForeignLang(lang) ? project.translations?.[lang]?.hours : undefined;

  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "";
  const proto = h.get("x-forwarded-proto") ?? "https";
  const pageUrl = `${proto}://${host}/s/${slug}${lang === langs[0] ? "" : `?lang=${lang}`}`;
  const jsonLd = hasPlace(project.place)
    ? localBusinessJsonLd(place, { url: pageUrl, lang, description: copy.hero?.subheadline ?? "" })
    : null;

  // 매장 안내 + 이메일 신청 — 템플릿 CTA의 #signup 앵커 대상. 템플릿 푸터 직전(slot)에 들어간다.
  const signupSlot = (
    <>
      <PlaceSection place={place} lang={lang} hours={translatedHours} />
      <section id="signup" className="bg-slate-900 px-6 py-20 text-center">
        <h2 className="text-2xl font-bold text-white sm:text-3xl">{copy?.cta?.headline || t.headline}</h2>
        <p className="mt-3 text-slate-300">{t.sub}</p>
        <div className="mt-8">
          <LeadForm projectId={project.id} buttonLabel={copy?.cta?.button || t.submit} operator={place.name} lang={lang} />
        </div>
      </section>
    </>
  );

  // 승인 기록이 없는 이전 게시물도 AI 표시는 기본으로 보인다(안전한 기본값).
  const compliance = project.compliance ?? {};

  return (
    <div lang={lang}>
      <ViewTracker projectId={project.id} />
      {jsonLd && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdString(jsonLd) }} />}
      {langs.length > 1 && (
        <nav aria-label={uiText(lang).language} className="flex flex-wrap justify-end gap-1 bg-slate-50 px-4 py-2 text-xs">
          {langs.map((l, i) => (
            <Link
              key={l}
              href={i === 0 ? `/s/${slug}` : `/s/${slug}?lang=${l}`}
              hrefLang={l}
              className={
                "rounded-full px-2.5 py-1 transition " +
                (l === lang ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200")
              }
            >
              {LANG_NAMES[l]}
            </Link>
          ))}
        </nav>
      )}
      <TemplateRenderer templateId={project.template} copy={copy} lang={lang} biz={project.biz_info} signupSlot={signupSlot} />
      <ComplianceFooter
        lang={lang}
        aiLabel={compliance.ai_label !== false}
        industry={isIndustryId(compliance.industry) ? compliance.industry : detectIndustry(project.biz_info)}
        disclosures={compliance.disclosures}
      />
    </div>
  );
}
