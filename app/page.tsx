// app/page.tsx  [신규] — PromptSite 마케팅 홈
import Link from "next/link";

const STEPS = [
  { n: "1", t: "한 줄로 설명", d: "무슨 사업·서비스인지 자유롭게 적어요." },
  { n: "2", t: "AI가 작성", d: "팔리는 카피와 어울리는 디자인을 만들어요." },
  { n: "3", t: "딸깍 게시", d: "공개 주소로 바로 띄우고 신청을 받아요." },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      {/* Nav */}
      <header className="border-b border-slate-100">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <span className="font-bold tracking-tight">
            Prompt<span className="text-indigo-600">Site</span>
          </span>
          <Link
            href="/project/new"
            className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
          >
            만들기 시작
          </Link>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1">
        <section className="bg-gradient-to-b from-indigo-50 to-white px-6 py-24 sm:py-32">
          <div className="mx-auto max-w-3xl text-center">
            <span className="inline-block rounded-full border border-indigo-200 bg-white px-4 py-1.5 text-sm font-medium text-indigo-700">
              프롬프트 한 줄 → 랜딩페이지
            </span>
            <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-6xl">
              랜딩페이지, <span className="text-indigo-600">딸깍</span> 한 번에
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-slate-600">
              무엇을 위한 페이지인지 적기만 하세요. 팔리는 카피, 어울리는 디자인,
              신청 폼까지 — AI가 만들어 바로 게시합니다.
            </p>
            <div className="mt-10 flex justify-center gap-3">
              <Link
                href="/project/new"
                className="rounded-full bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:bg-indigo-500"
              >
                지금 만들어보기
              </Link>
            </div>
            <p className="mt-3 text-sm text-slate-400">가입 없이 바로 체험할 수 있어요.</p>
          </div>
        </section>

        {/* How it works */}
        <section className="px-6 py-20">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">3단계면 충분해요</h2>
            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {STEPS.map((s) => (
                <div key={s.n} className="rounded-2xl border border-slate-200 p-6 text-center">
                  <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-xl font-bold text-indigo-600">
                    {s.n}
                  </div>
                  <h3 className="text-lg font-semibold">{s.t}</h3>
                  <p className="mt-2 text-slate-600">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-100 px-6 py-8">
        <div className="mx-auto max-w-5xl text-center text-sm text-slate-400">
          PromptSite — 딸깍으로 만드는 랜딩페이지
        </div>
      </footer>
    </div>
  );
}
