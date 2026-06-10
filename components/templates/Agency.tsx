// components/templates/Agency.tsx
// 대행/컨설팅/전문 서비스 템플릿. 신뢰 중심 split 히어로 + 번호 프로세스 + FAQ 2열 느낌.
// 순수 프레젠테이션(훅 없음). dangerouslySetInnerHTML 미사용.

import type { Lang } from "@/lib/ai/types";
import { THEMES } from "@/lib/ai/theme";
import type { TemplateProps } from "./SaasLaunch";
import { FeatureIcon } from "./icons";

export default function Agency({ copy, lang = "ko", theme = THEMES.violet, brand = "", signupSlot }: TemplateProps) {
  const t =
    lang === "en"
      ? { faq: "FAQ", process: "How we work", consult: "Free consultation" }
      : { faq: "자주 묻는 질문", process: "진행 방식", consult: "부담 없는 상담부터" };
  const langTyped: Lang = lang;

  return (
    <div className="bg-white text-slate-900">
      {/* Nav */}
      {brand && (
        <header className="border-b border-slate-100">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <span className="flex items-center gap-2 font-bold tracking-tight">
              <span className={`h-2.5 w-2.5 rounded-full ${theme.bar}`} />
              {brand}
            </span>
            <a
              href="#signup"
              className={`rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-md transition ${theme.btnPrimary}`}
            >
              {copy.hero.cta}
            </a>
          </div>
        </header>
      )}

      {/* Hero — split */}
      <section className="relative overflow-hidden border-b border-slate-100 px-6 py-20 sm:py-28">
        <div className={`pointer-events-none absolute inset-0 ${theme.heroGlow}`} />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <span className={`animate-fade-up inline-block rounded-full border px-4 py-1.5 text-sm font-medium ${theme.badge}`}>
              {brand || t.consult}
            </span>
            <h1 className="animate-fade-up-delay-1 mt-6 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
              {copy.hero.headline}
            </h1>
            {copy.hero.subheadline && (
              <p className="animate-fade-up-delay-2 mt-6 max-w-xl text-lg leading-8 text-slate-600">
                {copy.hero.subheadline}
              </p>
            )}
            <div className="animate-fade-up-delay-2 mt-8 flex flex-wrap items-center gap-4">
              <a
                href="#signup"
                className={`rounded-lg px-7 py-3.5 font-semibold text-white shadow-lg transition ${theme.btnPrimary}`}
              >
                {copy.hero.cta}
              </a>
              <span className="text-sm text-slate-400">{t.consult}</span>
            </div>
          </div>

          {/* 오른쪽 신뢰 카드: 문제 공감 + 핵심 항목 미리보기 */}
          <div className="animate-fade-up-delay-2 space-y-4">
            {copy.problem.body && (
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-7">
                {copy.problem.title && <h2 className="text-lg font-bold">{copy.problem.title}</h2>}
                <p className="mt-2 leading-7 text-slate-600">{copy.problem.body}</p>
              </div>
            )}
            {copy.features.items.slice(0, 2).map((f, i) => (
              <div key={i} className="flex items-start gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${theme.iconChip}`}>
                  <FeatureIcon i={i} />
                </span>
                <div>
                  <p className="font-semibold">{f.title}</p>
                  {f.description && <p className="mt-1 text-sm leading-6 text-slate-500">{f.description}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Solution */}
      {copy.solution.body && (
        <section className="px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-3xl">
            <div className={`mb-5 h-1.5 w-16 rounded ${theme.bar}`} />
            {copy.solution.title && <h2 className="text-2xl font-bold sm:text-3xl">{copy.solution.title}</h2>}
            <p className="mt-4 text-lg leading-8 text-slate-600">{copy.solution.body}</p>
          </div>
        </section>
      )}

      {/* Process — 번호 단계 */}
      {copy.features.items.length > 0 && (
        <section className="bg-slate-50 px-6 py-16 sm:py-24">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-2xl font-bold sm:text-4xl">{copy.features.title || t.process}</h2>
            <div className="mt-10 space-y-4">
              {copy.features.items.map((f, i) => (
                <div
                  key={i}
                  className="flex gap-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:shadow-md sm:p-7"
                >
                  <span className={`text-3xl font-extrabold tabular-nums ${theme.accentText}`}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <h3 className="text-lg font-semibold">{f.title}</h3>
                    {f.description && <p className="mt-1 leading-7 text-slate-600">{f.description}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      {copy.faq.length > 0 && (
        <section className="px-6 py-16 sm:py-24">
          <div className="mx-auto max-w-3xl">
            <h2 className="text-2xl font-bold sm:text-4xl">{t.faq}</h2>
            <div className="mt-8 space-y-3">
              {copy.faq.map((q, i) => (
                <details key={i} className="group rounded-2xl border border-slate-200 bg-white px-6 py-4 open:shadow-sm">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
                    {q.question}
                    <span className={`shrink-0 text-xl transition group-open:rotate-45 ${theme.accentText}`}>+</span>
                  </summary>
                  <p className="mt-3 leading-7 text-slate-600">{q.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="relative overflow-hidden bg-slate-900 px-6 py-16 text-center sm:py-20">
        <div className={`pointer-events-none absolute inset-0 ${theme.heroGlowDark}`} />
        <h2 className="relative text-2xl font-bold text-white sm:text-4xl">{copy.cta.headline}</h2>
        <div className="relative mt-8">
          <a
            href="#signup"
            className={`inline-block rounded-lg px-7 py-3.5 font-semibold text-white shadow-lg transition ${theme.btnPrimary}`}
          >
            {copy.cta.button}
          </a>
        </div>
      </section>

      {signupSlot}

      {/* Footer */}
      <footer className="border-t border-slate-100 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 text-sm text-slate-400 sm:flex-row">
          <span className="flex items-center gap-2 font-semibold text-slate-500">
            {brand && <span className={`h-2 w-2 rounded-full ${theme.bar}`} />}
            {brand}
          </span>
          <span>
            © {new Date().getFullYear()} {brand || (langTyped === "en" ? "Agency" : "에이전시")}. All rights reserved.
          </span>
        </div>
      </footer>
    </div>
  );
}
