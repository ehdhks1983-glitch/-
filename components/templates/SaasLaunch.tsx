// components/templates/SaasLaunch.tsx  [신규]
// SaaS/제품 출시 템플릿. SectionCopy를 받아 hero/problem/solution/features/faq/cta를 렌더.
// 순수 프레젠테이션(훅 없음, FAQ는 네이티브 <details>). dangerouslySetInnerHTML 미사용.

import type { Lang, SectionCopy } from "@/lib/ai/types";

export default function SaasLaunch({ copy, lang = "ko" }: { copy: SectionCopy; lang?: Lang }) {
  const faqHeading = lang === "en" ? "FAQ" : "자주 묻는 질문";

  return (
    <div className="bg-white text-slate-900">
      {/* Hero */}
      <section className="overflow-hidden bg-gradient-to-b from-indigo-50 to-white px-6 py-20 sm:py-28">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">{copy.hero.headline}</h1>
          {copy.hero.subheadline && (
            <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-600">{copy.hero.subheadline}</p>
          )}
          <div className="mt-10 flex justify-center">
            <a
              href="#signup"
              className="rounded-full bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:bg-indigo-500"
            >
              {copy.hero.cta}
            </a>
          </div>
        </div>
      </section>

      {/* Problem */}
      {copy.problem.body && (
        <section className="px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-2xl text-center">
            {copy.problem.title && <h2 className="text-2xl font-bold sm:text-3xl">{copy.problem.title}</h2>}
            <p className="mt-4 text-lg leading-8 text-slate-600">{copy.problem.body}</p>
          </div>
        </section>
      )}

      {/* Solution */}
      {copy.solution.body && (
        <section className="bg-slate-50 px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-2xl text-center">
            {copy.solution.title && <h2 className="text-2xl font-bold sm:text-3xl">{copy.solution.title}</h2>}
            <p className="mt-4 text-lg leading-8 text-slate-600">{copy.solution.body}</p>
          </div>
        </section>
      )}

      {/* Features */}
      {copy.features.items.length > 0 && (
        <section className="px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-5xl">
            {copy.features.title && (
              <h2 className="text-center text-2xl font-bold sm:text-3xl">{copy.features.title}</h2>
            )}
            <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {copy.features.items.map((f, i) => (
                <div key={i} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-100 font-bold text-indigo-600">
                    {i + 1}
                  </div>
                  <h3 className="text-lg font-semibold">{f.title}</h3>
                  {f.description && <p className="mt-2 text-slate-600">{f.description}</p>}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      {copy.faq.length > 0 && (
        <section className="bg-slate-50 px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-2xl">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">{faqHeading}</h2>
            <div className="mt-10 divide-y divide-slate-200">
              {copy.faq.map((q, i) => (
                <details key={i} className="group py-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                    {q.question}
                    <span className="ml-4 text-indigo-600 transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-slate-600">{q.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section id="cta" className="bg-indigo-600 px-6 py-16 sm:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-2xl font-bold text-white sm:text-3xl">{copy.cta.headline}</h2>
          <div className="mt-8 flex justify-center">
            <a
              href="#signup"
              className="rounded-full bg-white px-8 py-3.5 text-base font-semibold text-indigo-600 shadow-lg transition hover:bg-indigo-50"
            >
              {copy.cta.button}
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
