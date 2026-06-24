// app/page.tsx — 곰대리 멀티발행 랜딩(마케팅 홈). CTA → /workspace (미로그인 시 proxy가 /login 으로).
import Link from "next/link";

const STEPS = [
  { n: "1", t: "키워드 + 참고자료", d: "쓰고 싶은 키워드와 참고 URL만 넣어요." },
  { n: "2", t: "코어 추출", d: "참고자료에서 핵심 메시지·사실·앵글을 뽑아요." },
  { n: "3", t: "블로그 + 4채널", d: "SEO 블로그와 스레드·인스타·카페·쇼츠를 한 번에." },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-stone-900">
      <header className="border-b border-stone-100">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <span className="flex items-center gap-2 font-extrabold tracking-tight">
            <span aria-hidden className="text-xl">🐻</span>
            곰대리 <span className="font-semibold text-emerald-700">멀티발행</span>
          </span>
          <Link
            href="/workspace"
            className="rounded-full bg-stone-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-stone-700"
          >
            시작하기
          </Link>
        </div>
      </header>

      <main className="flex-1">
        <section className="bg-gradient-to-b from-emerald-50 to-white px-6 py-24 sm:py-32">
          <div className="mx-auto max-w-3xl text-center">
            <span className="inline-block rounded-full border border-emerald-200 bg-white px-4 py-1.5 text-sm font-medium text-emerald-800">
              키워드 하나 → 블로그 + 스레드·인스타·카페·쇼츠
            </span>
            <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-6xl">
              한 번 쓰면, <span className="text-emerald-700">5채널</span>로 퍼집니다
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-stone-600">
              키워드와 참고자료에서 핵심(코어)을 뽑아, 채널마다 어울리는 글로 바꿔드려요.
              블로그는 SEO 포맷, 나머지는 채널 native하게. 발행은 복붙이면 끝이에요.
            </p>
            <div className="mt-10 flex justify-center gap-3">
              <Link
                href="/workspace"
                className="rounded-full bg-emerald-600 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-emerald-600/20 transition hover:bg-emerald-500"
              >
                새 발행 시작
              </Link>
            </div>
            <p className="mt-3 text-sm text-stone-400">가입하면 체험 포인트를 드려요.</p>
          </div>
        </section>

        <section className="px-6 py-20">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">3단계면 충분해요</h2>
            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {STEPS.map((s) => (
                <div key={s.n} className="rounded-2xl border border-stone-200 p-6 text-center">
                  <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-xl font-bold text-emerald-700">
                    {s.n}
                  </div>
                  <h3 className="text-lg font-semibold">{s.t}</h3>
                  <p className="mt-2 text-stone-600">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-stone-100 px-6 py-8">
        <div className="mx-auto max-w-5xl text-center text-sm text-stone-400">
          곰대리 멀티발행 · 결과 생성만, 발행은 사용자 복붙 (계정/ToS 리스크 0)
        </div>
      </footer>
    </div>
  );
}
