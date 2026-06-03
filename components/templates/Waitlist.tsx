// components/templates/Waitlist.tsx  [신규]
// 사전 등록/대기자 모집 템플릿. 미니멀·다크, 신청(CTA) 중심.
// 순수 프레젠테이션(훅 없음). dangerouslySetInnerHTML 미사용.

import type { Lang, SectionCopy } from "@/lib/ai/types";

export default function Waitlist({ copy, lang = "ko" }: { copy: SectionCopy; lang?: Lang }) {
  const t =
    lang === "en"
      ? { badge: "Coming soon", why: "Why join", faq: "FAQ" }
      : { badge: "곧 출시", why: "왜 지금인가", faq: "자주 묻는 질문" };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Hero */}
      <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 py-20 text-center">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(99,102,241,0.25),transparent)]" />
        <div className="relative mx-auto max-w-2xl">
          <span className="inline-block rounded-full border border-indigo-400/30 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300">
            {t.badge}
          </span>
          <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-6xl">{copy.hero.headline}</h1>
          {copy.hero.subheadline && (
            <p className="mx-auto mt-6 max-w-xl text-lg text-slate-300">{copy.hero.subheadline}</p>
          )}
          <div className="mt-10 flex justify-center">
            <a
              href="#signup"
              className="rounded-full bg-indigo-500 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:bg-indigo-400"
            >
              {copy.hero.cta}
            </a>
          </div>
        </div>
      </section>

      {/* Why (solution/problem) */}
      {(copy.solution.body || copy.problem.body) && (
        <section className="border-t border-white/5 px-6 py-16">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-2xl font-bold sm:text-3xl">{copy.solution.title || t.why}</h2>
            <p className="mt-4 text-lg leading-8 text-slate-300">{copy.solution.body || copy.problem.body}</p>
          </div>
        </section>
      )}

      {/* Features (checklist) */}
      {copy.features.items.length > 0 && (
        <section className="px-6 pb-16">
          <div className="mx-auto max-w-xl">
            <ul className="space-y-4">
              {copy.features.items.map((f, i) => (
                <li key={i} className="flex gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-300">
                    ✓
                  </span>
                  <div>
                    <p className="font-semibold">{f.title}</p>
                    {f.description && <p className="text-slate-400">{f.description}</p>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* FAQ */}
      {copy.faq.length > 0 && (
        <section className="border-t border-white/5 px-6 py-16">
          <div className="mx-auto max-w-2xl">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">{t.faq}</h2>
            <div className="mt-8 divide-y divide-white/10">
              {copy.faq.map((q, i) => (
                <details key={i} className="group py-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                    {q.question}
                    <span className="ml-4 text-indigo-400 transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-slate-400">{q.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="px-6 py-20 text-center">
        <h2 className="text-2xl font-bold sm:text-3xl">{copy.cta.headline}</h2>
        <div className="mt-8 flex justify-center">
          <a
            href="#signup"
            className="rounded-full bg-indigo-500 px-8 py-3.5 font-semibold text-white transition hover:bg-indigo-400"
          >
            {copy.cta.button}
          </a>
        </div>
      </section>
    </div>
  );
}
