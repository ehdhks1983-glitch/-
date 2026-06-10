// components/templates/Waitlist.tsx
// 사전 등록/대기자 모집 템플릿. 다크·미니멀, 글로우 히어로 + 체크리스트 + FAQ.
// 순수 프레젠테이션(훅 없음). dangerouslySetInnerHTML 미사용.

import type { Lang } from "@/lib/ai/types";
import { THEMES } from "@/lib/ai/theme";
import type { TemplateProps } from "./SaasLaunch";
import { CheckIcon } from "./icons";

export default function Waitlist({ copy, lang = "ko", theme = THEMES.indigo, brand = "", signupSlot }: TemplateProps) {
  const t =
    lang === "en"
      ? { badge: "Coming soon", why: "Why join", faq: "FAQ", spots: "Early access — limited spots" }
      : { badge: "곧 출시", why: "왜 지금인가", faq: "자주 묻는 질문", spots: "사전 등록자에게 가장 먼저 알려드려요" };
  const langTyped: Lang = lang;

  return (
    <div className="bg-slate-950 text-slate-100">
      {/* Nav */}
      {brand && (
        <header className="border-b border-white/5">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
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
      <section className="relative flex min-h-[88vh] flex-col items-center justify-center overflow-hidden px-6 py-24 text-center">
        <div className={`pointer-events-none absolute inset-0 ${theme.heroGlowDark}`} />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:radial-gradient(55%_45%_at_50%_30%,black,transparent)]" />
        <div className="relative mx-auto max-w-2xl">
          <span className={`animate-fade-up inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-medium ${theme.badgeOnDark}`}>
            <span className="relative flex h-2 w-2">
              <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${theme.bar}`} />
              <span className={`relative inline-flex h-2 w-2 rounded-full ${theme.bar}`} />
            </span>
            {t.badge}
          </span>
          <h1 className="animate-fade-up-delay-1 mt-6 text-4xl font-extrabold leading-tight tracking-tight sm:text-6xl">
            {copy.hero.headline}
          </h1>
          {copy.hero.subheadline && (
            <p className="animate-fade-up-delay-2 mx-auto mt-6 max-w-xl text-lg leading-8 text-slate-300">
              {copy.hero.subheadline}
            </p>
          )}
          <div className="animate-fade-up-delay-2 mt-10 flex justify-center">
            <a
              href="#signup"
              className={`rounded-full px-8 py-3.5 text-base font-semibold text-white shadow-lg transition ${theme.btnPrimary}`}
            >
              {copy.hero.cta}
            </a>
          </div>
          <p className="mt-4 text-sm text-slate-500">{t.spots}</p>
        </div>
      </section>

      {/* Why (problem → solution 흐름) */}
      {(copy.problem.body || copy.solution.body) && (
        <section className="border-t border-white/5 px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-2xl space-y-10 text-center">
            {copy.problem.body && (
              <div>
                {copy.problem.title && <h2 className="text-xl font-bold text-slate-300 sm:text-2xl">{copy.problem.title}</h2>}
                <p className="mt-3 text-lg leading-8 text-slate-400">{copy.problem.body}</p>
              </div>
            )}
            {copy.solution.body && (
              <div className="rounded-3xl border border-white/10 bg-white/5 p-8 sm:p-10">
                <h2 className={`text-2xl font-bold sm:text-3xl ${theme.accentTextOnDark}`}>
                  {copy.solution.title || t.why}
                </h2>
                <p className="mt-4 text-lg leading-8 text-slate-300">{copy.solution.body}</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Features (체크리스트) */}
      {copy.features.items.length > 0 && (
        <section className="px-6 pb-16 sm:pb-20">
          <div className="mx-auto max-w-xl">
            {copy.features.title && (
              <h2 className="mb-8 text-center text-2xl font-bold sm:text-3xl">{copy.features.title}</h2>
            )}
            <ul className="space-y-4">
              {copy.features.items.map((f, i) => (
                <li key={i} className="flex gap-4 rounded-2xl border border-white/10 bg-white/5 p-5">
                  <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${theme.iconChipOnDark}`}>
                    <CheckIcon />
                  </span>
                  <div>
                    <p className="font-semibold">{f.title}</p>
                    {f.description && <p className="mt-1 leading-7 text-slate-400">{f.description}</p>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* FAQ */}
      {copy.faq.length > 0 && (
        <section className="border-t border-white/5 px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-2xl">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">{t.faq}</h2>
            <div className="mt-8 space-y-3">
              {copy.faq.map((q, i) => (
                <details key={i} className="group rounded-2xl border border-white/10 bg-white/5 px-6 py-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
                    {q.question}
                    <span className={`shrink-0 text-xl transition group-open:rotate-45 ${theme.accentTextOnDark}`}>+</span>
                  </summary>
                  <p className="mt-3 leading-7 text-slate-400">{q.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="relative overflow-hidden px-6 py-20 text-center">
        <div className={`pointer-events-none absolute inset-0 ${theme.heroGlowDark}`} />
        <h2 className="relative text-2xl font-bold sm:text-4xl">{copy.cta.headline}</h2>
        <div className="relative mt-8 flex justify-center">
          <a
            href="#signup"
            className={`rounded-full px-8 py-3.5 font-semibold text-white shadow-lg transition ${theme.btnPrimary}`}
          >
            {copy.cta.button}
          </a>
        </div>
      </section>

      {signupSlot}

      {/* Footer */}
      <footer className="border-t border-white/5 px-6 py-10">
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-3 text-sm text-slate-500 sm:flex-row">
          <span className="font-semibold text-slate-400">{brand}</span>
          <span>
            © {new Date().getFullYear()} {brand || (langTyped === "en" ? "Waitlist" : "사전등록")}. All rights reserved.
          </span>
        </div>
      </footer>
    </div>
  );
}
