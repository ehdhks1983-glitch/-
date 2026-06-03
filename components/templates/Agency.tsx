// components/templates/Agency.tsx  [신규]
// 대행/컨설팅/전문 서비스 템플릿. 신뢰 중심, 라이트·에메랄드 액센트.
// 순수 프레젠테이션(훅 없음). dangerouslySetInnerHTML 미사용.

import type { Lang, SectionCopy } from "@/lib/ai/types";

export default function Agency({ copy, lang = "ko" }: { copy: SectionCopy; lang?: Lang }) {
  const faqHeading = lang === "en" ? "FAQ" : "자주 묻는 질문";

  return (
    <div className="bg-white text-slate-900">
      {/* Hero */}
      <section className="border-b border-slate-100 px-6 py-20 sm:py-28">
        <div className="mx-auto grid max-w-5xl items-center gap-10 lg:grid-cols-2">
          <div>
            <div className="mb-5 h-1.5 w-16 rounded bg-emerald-500" />
            <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">{copy.hero.headline}</h1>
            {copy.hero.subheadline && (
              <p className="mt-6 text-lg leading-8 text-slate-600">{copy.hero.subheadline}</p>
            )}
            <div className="mt-8">
              <a
                href="#signup"
                className="inline-block rounded-lg bg-emerald-600 px-7 py-3.5 font-semibold text-white shadow-sm transition hover:bg-emerald-500"
              >
                {copy.hero.cta}
              </a>
            </div>
          </div>
          {copy.problem.body && (
            <div className="rounded-2xl bg-gradient-to-br from-emerald-50 to-slate-50 p-8">
              {copy.problem.title && <h2 className="text-xl font-bold">{copy.problem.title}</h2>}
              <p className="mt-3 leading-7 text-slate-600">{copy.problem.body}</p>
            </div>
          )}
        </div>
      </section>

      {/* Solution */}
      {copy.solution.body && (
        <section className="px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-3xl">
            {copy.solution.title && <h2 className="text-2xl font-bold sm:text-3xl">{copy.solution.title}</h2>}
            <p className="mt-4 text-lg leading-8 text-slate-600">{copy.solution.body}</p>
          </div>
        </section>
      )}

      {/* Features (numbered rows) */}
      {copy.features.items.length > 0 && (
        <section className="bg-slate-50 px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-4xl">
            {copy.features.title && <h2 className="text-2xl font-bold sm:text-3xl">{copy.features.title}</h2>}
            <div className="mt-10 space-y-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200">
              {copy.features.items.map((f, i) => (
                <div key={i} className="flex gap-5 bg-white p-6">
                  <span className="text-2xl font-bold text-emerald-600">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <h3 className="text-lg font-semibold">{f.title}</h3>
                    {f.description && <p className="mt-1 text-slate-600">{f.description}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      {copy.faq.length > 0 && (
        <section className="px-6 py-16 sm:py-20">
          <div className="mx-auto max-w-3xl">
            <h2 className="text-2xl font-bold sm:text-3xl">{faqHeading}</h2>
            <div className="mt-8 divide-y divide-slate-200">
              {copy.faq.map((q, i) => (
                <details key={i} className="group py-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                    {q.question}
                    <span className="ml-4 text-emerald-600 transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-slate-600">{q.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="bg-slate-900 px-6 py-16 text-center sm:py-20">
        <h2 className="text-2xl font-bold text-white sm:text-3xl">{copy.cta.headline}</h2>
        <div className="mt-8">
          <a
            href="#signup"
            className="inline-block rounded-lg bg-emerald-500 px-7 py-3.5 font-semibold text-white transition hover:bg-emerald-400"
          >
            {copy.cta.button}
          </a>
        </div>
      </section>
    </div>
  );
}
