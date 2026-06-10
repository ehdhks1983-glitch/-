// components/templates/SaasLaunch.tsx
// SaaS/제품 출시 템플릿. 내비+히어로(글로우·배지·듀얼 CTA)+문제/해결 카드+아이콘 기능 그리드+FAQ+CTA+푸터.
// 순수 프레젠테이션(훅 없음). dangerouslySetInnerHTML 미사용.

import type { ReactNode } from "react";
import type { Lang, SectionCopy } from "@/lib/ai/types";
import { THEMES, type Theme } from "@/lib/ai/theme";
import { FeatureIcon } from "./icons";

export interface TemplateProps {
  copy: SectionCopy;
  lang?: Lang;
  theme?: Theme;
  brand?: string;
  signupSlot?: ReactNode;
}

export default function SaasLaunch({ copy, lang = "ko", theme = THEMES.indigo, brand = "", signupSlot }: TemplateProps) {
  const t =
    lang === "en"
      ? { faq: "FAQ", features: "Features", free: "No credit card required" }
      : { faq: "자주 묻는 질문", features: "핵심 기능", free: "부담 없이 시작하세요" };

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
              className={`rounded-full px-4 py-2 text-sm font-semibold text-white shadow-md transition ${theme.btnPrimary}`}
            >
              {copy.hero.cta}
            </a>
          </div>
        </header>
      )}

      {/* Hero */}
      <section className="relative overflow-hidden px-6 pb-20 pt-16 sm:pb-28 sm:pt-24">
        <div className={`pointer-events-none absolute inset-0 ${theme.heroGlow}`} />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(15,23,42,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(15,23,42,0.04)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:radial-gradient(60%_50%_at_50%_0%,black,transparent)]" />
        <div className="relative mx-auto max-w-3xl text-center">
          <span className={`animate-fade-up inline-block rounded-full border px-4 py-1.5 text-sm font-medium ${theme.badge}`}>
            {brand || copy.hero.cta}
          </span>
          <h1 className="animate-fade-up-delay-1 mt-6 text-4xl font-extrabold leading-tight tracking-tight sm:text-6xl">
            {copy.hero.headline}
          </h1>
          {copy.hero.subheadline && (
            <p className="animate-fade-up-delay-2 mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-600">
              {copy.hero.subheadline}
            </p>
          )}
          <div className="animate-fade-up-delay-2 mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="#signup"
              className={`rounded-full px-8 py-3.5 text-base font-semibold text-white shadow-lg transition ${theme.btnPrimary}`}
            >
              {copy.hero.cta}
            </a>
            {copy.features.items.length > 0 && (
              <a
                href="#features"
                className="rounded-full border border-slate-200 bg-white px-8 py-3.5 text-base font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
              >
                {t.features} ↓
              </a>
            )}
          </div>
          <p className="mt-4 text-sm text-slate-400">{t.free}</p>
        </div>
      </section>

      {/* Problem / Solution — 대비 카드 2열 */}
      {(copy.problem.body || copy.solution.body) && (
        <section className="px-6 py-16 sm:py-20">
          <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-2">
            {copy.problem.body && (
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-8 sm:p-10">
                <div className="mb-4 h-1.5 w-12 rounded bg-slate-300" />
                {copy.problem.title && <h2 className="text-2xl font-bold">{copy.problem.title}</h2>}
                <p className="mt-4 text-lg leading-8 text-slate-600">{copy.problem.body}</p>
              </div>
            )}
            {copy.solution.body && (
              <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
                <div className={`mb-4 h-1.5 w-12 rounded ${theme.bar}`} />
                {copy.solution.title && (
                  <h2 className="text-2xl font-bold">
                    <span className={theme.accentText}>{copy.solution.title}</span>
                  </h2>
                )}
                <p className="mt-4 text-lg leading-8 text-slate-600">{copy.solution.body}</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Features */}
      {copy.features.items.length > 0 && (
        <section id="features" className="bg-slate-50 px-6 py-16 sm:py-24">
          <div className="mx-auto max-w-5xl">
            {copy.features.title && (
              <h2 className="text-center text-2xl font-bold sm:text-4xl">{copy.features.title}</h2>
            )}
            <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {copy.features.items.map((f, i) => (
                <div
                  key={i}
                  className="group rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-md"
                >
                  <div className={`mb-4 flex h-11 w-11 items-center justify-center rounded-xl ${theme.iconChip}`}>
                    <FeatureIcon i={i} />
                  </div>
                  <h3 className="text-lg font-semibold">{f.title}</h3>
                  {f.description && <p className="mt-2 leading-7 text-slate-600">{f.description}</p>}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      {copy.faq.length > 0 && (
        <section className="px-6 py-16 sm:py-24">
          <div className="mx-auto max-w-2xl">
            <h2 className="text-center text-2xl font-bold sm:text-4xl">{t.faq}</h2>
            <div className="mt-10 space-y-3">
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
      <section className="px-6 pb-20">
        <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl bg-slate-900 px-6 py-16 text-center sm:py-20">
          <div className={`pointer-events-none absolute inset-0 ${theme.heroGlowDark}`} />
          <h2 className="relative text-2xl font-bold text-white sm:text-4xl">{copy.cta.headline}</h2>
          <div className="relative mt-8 flex justify-center">
            <a
              href="#signup"
              className={`rounded-full px-8 py-3.5 text-base font-semibold text-white shadow-lg transition ${theme.btnPrimary}`}
            >
              {copy.cta.button}
            </a>
          </div>
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
          <span>© {new Date().getFullYear()} {brand || "Landing"}. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
}
