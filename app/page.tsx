// app/page.tsx — 머무는순간 마케팅 홈.
import Link from "next/link";
import Nav from "@/components/site/Nav";
import Footer from "@/components/site/Footer";
import { BRAND, PACKAGES } from "@/lib/brand";
import { ShieldCheck, Sparkles, Curate, Play, Home as HomeIcon, Check } from "@/components/site/icons";

const PAINS = [
  "숏폼? 만들 줄도 모르고, 외주 영상은 너무 비싸요.",
  "인스타·네이버 클립에 올려도 노출이 안 돼요.",
  "체험단 썼다가 뒷광고로 걸릴까 봐 무서워요.",
];

const AXES = [
  {
    icon: ShieldCheck,
    tag: "간판 차별점",
    title: "공정위 100% 합법",
    body: "모든 콘텐츠 제목·본문 첫 줄에 ‘광고/협찬’ 자동 표기. 실제 1박 체험만, 가짜 후기 0건. 광고주 보호 약정서로 리스크를 0으로 만듭니다.",
  },
  {
    icon: Curate,
    tag: "품질",
    title: "큐레이션 + 느슨한 전속",
    body: "신청한다고 다 받지 않습니다. 비주얼 심사를 통과한 감성 스테이만. 검증된 크리에이터에게 좋은 캠페인을 먼저 배정합니다.",
  },
  {
    icon: Sparkles,
    tag: "물량 무기",
    title: "AI 소재 변형",
    body: "실제로 찍은 숏폼 1개를 받아 광고·예약페이지용 변형 N개를 생성. 진정성(실제 1박)과 물량(AI 변형)을 동시에 제공합니다.",
  },
];

const STEPS = [
  { icon: HomeIcon, t: "숙소 신청 · 심사", d: "감성 스테이가 신청하면 비주얼 큐레이션 심사를 거쳐요." },
  { icon: Curate, t: "크리에이터 매칭", d: "지역·카테고리·퀄리티 기준으로 적합한 크리에이터를 배정해요." },
  { icon: Play, t: "실제 1박 · 촬영", d: "직접 자고 찍은 9:16 숏폼을 릴스·네이버 클립에 동시 업로드." },
  { icon: Sparkles, t: "AI 소재 + 리포트", d: "영상 1개를 광고·예약용 변형으로 확장하고 성과를 정리해요." },
];

const FAQ = [
  {
    q: "정말 공정위에 안 걸리나요?",
    a: "모든 콘텐츠의 제목 또는 본문 첫 줄에 ‘광고/협찬’을 표기하고, 실제 1박 체험 후에만 촬영합니다. 표시광고법·추천보증 심사지침을 100% 준수하며 광고주 보호 약정서를 제공합니다.",
  },
  {
    q: "어떤 숙소를 받나요?",
    a: "감성 독채 펜션·풀빌라·한옥스테이·디자인 스테이 등 비주얼이 강한 스테이를 우선합니다. 모텔·비즈니스호텔·대형 리조트는 받지 않습니다.",
  },
  {
    q: "크리에이터 보상은 어떻게 되나요?",
    a: "1박 무료 숙박(현물)이 기본 보상이며, 캠페인에 따라 소액 원고료가 추가될 수 있습니다. 네이버 클립 크리에이터를 우선 매칭합니다.",
  },
  {
    q: "비용은 얼마인가요?",
    a: "패키지에 따라 20만~150만원 수준이며 AI 소재팩·리포트 옵션을 더할 수 있습니다. 아래 요금표를 참고하세요.",
  },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <Nav />

      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(13,148,136,0.10),transparent)]" />
          <div className="relative mx-auto max-w-3xl px-6 py-24 text-center sm:py-32">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-teal-200 bg-white px-4 py-1.5 text-sm font-medium text-teal-800">
              <ShieldCheck className="h-4 w-4" />
              {BRAND.tagline}
            </span>
            <h1 className="mt-7 text-4xl font-bold leading-tight tracking-tight sm:text-6xl">
              감성 스테이를,
              <br />
              <span className="text-teal-700">숏폼</span>으로 알리는 가장 합법적인 방법
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-stone-600">{BRAND.oneLiner}</p>
            <div className="mt-10 flex flex-col justify-center gap-3 sm:flex-row">
              <Link
                href="/apply/host"
                className="rounded-full bg-teal-700 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-teal-700/20 transition hover:bg-teal-800"
              >
                숙소 캠페인 신청
              </Link>
              <Link
                href="/apply/creator"
                className="rounded-full border border-stone-300 bg-white px-8 py-3.5 text-base font-semibold text-stone-800 transition hover:border-stone-400"
              >
                크리에이터로 합류
              </Link>
            </div>
            <p className="mt-4 text-sm text-stone-400">{BRAND.defaultRegionNote}</p>
          </div>
        </section>

        {/* Trust badges */}
        <section className="border-y border-stone-200 bg-white">
          <div className="mx-auto grid max-w-4xl grid-cols-1 gap-px overflow-hidden text-center sm:grid-cols-3">
            {[
              { t: "공정위 100% 합법", d: "표기 강제 · 가짜 후기 0건" },
              { t: "실제 1박 체험", d: "AI가 못 먹는 진정성의 칸" },
              { t: "큐레이션", d: "비주얼 심사 통과한 곳만" },
            ].map((b) => (
              <div key={b.t} className="px-6 py-7">
                <p className="font-semibold text-stone-900">{b.t}</p>
                <p className="mt-1 text-sm text-stone-500">{b.d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Pain → who it's for */}
        <section className="mx-auto max-w-4xl px-6 py-20">
          <div className="grid items-center gap-10 md:grid-cols-2">
            <div>
              <h2 className="text-2xl font-bold sm:text-3xl">이런 고민, 있으셨죠?</h2>
              <p className="mt-3 text-stone-600">
                감성 독채 펜션·풀빌라·한옥스테이 운영자가 가장 많이 겪는 문제예요.
              </p>
            </div>
            <ul className="space-y-3">
              {PAINS.map((p) => (
                <li key={p} className="rounded-xl border border-stone-200 bg-white px-5 py-4 text-stone-700">
                  “{p}”
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 3 axes */}
        <section className="bg-white py-20">
          <div className="mx-auto max-w-5xl px-6">
            <div className="text-center">
              <h2 className="text-2xl font-bold sm:text-3xl">세 가지로 다릅니다</h2>
              <p className="mt-3 text-stone-600">합법을 전면 간판으로, 큐레이션과 AI를 무기로 받칩니다.</p>
            </div>
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {AXES.map((a) => (
                <div key={a.title} className="rounded-2xl border border-stone-200 bg-stone-50 p-7">
                  <div className="inline-flex rounded-xl bg-teal-100 p-3 text-teal-700">
                    <a.icon />
                  </div>
                  <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-teal-700">{a.tag}</p>
                  <h3 className="mt-1 text-lg font-bold">{a.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">{a.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="mx-auto max-w-5xl scroll-mt-20 px-6 py-20">
          <div className="text-center">
            <h2 className="text-2xl font-bold sm:text-3xl">어떻게 진행되나요</h2>
            <p className="mt-3 text-stone-600">신청부터 성과 리포트까지 4단계.</p>
          </div>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.t} className="rounded-2xl border border-stone-200 bg-white p-6">
                <div className="flex items-center justify-between">
                  <span className="inline-flex rounded-lg bg-teal-100 p-2.5 text-teal-700">
                    <s.icon className="h-5 w-5" />
                  </span>
                  <span className="text-3xl font-bold text-stone-200">{i + 1}</span>
                </div>
                <h3 className="mt-4 font-bold">{s.t}</h3>
                <p className="mt-1.5 text-sm leading-6 text-stone-600">{s.d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Packages */}
        <section id="packages" className="scroll-mt-20 bg-white py-20">
          <div className="mx-auto max-w-5xl px-6">
            <div className="text-center">
              <h2 className="text-2xl font-bold sm:text-3xl">요금 안내</h2>
              <p className="mt-3 text-stone-600">
                큐레이션 + 합법 + AI팩으로 가치를 만듭니다. (현물 1박은 광고주 제공, 대행료는 아래 기준)
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              {PACKAGES.map((p) => (
                <div
                  key={p.id}
                  className={`relative rounded-2xl border p-7 ${
                    p.featured
                      ? "border-teal-600 bg-teal-50 shadow-lg shadow-teal-700/10"
                      : "border-stone-200 bg-stone-50"
                  }`}
                >
                  {p.featured && (
                    <span className="absolute -top-3 left-7 rounded-full bg-teal-700 px-3 py-1 text-xs font-semibold text-white">
                      가장 추천
                    </span>
                  )}
                  <h3 className="text-lg font-bold">{p.name}</h3>
                  <p className="mt-1 text-sm text-stone-500">{p.summary}</p>
                  <p className="mt-4 text-2xl font-bold text-stone-900">{p.price}</p>
                  <ul className="mt-5 space-y-2.5">
                    {p.items.map((it) => (
                      <li key={it} className="flex items-start gap-2 text-sm text-stone-700">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
                        <span>{it}</span>
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/apply/host"
                    className={`mt-7 block rounded-xl px-5 py-3 text-center text-sm font-semibold transition ${
                      p.featured
                        ? "bg-teal-700 text-white hover:bg-teal-800"
                        : "border border-stone-300 bg-white text-stone-800 hover:border-stone-400"
                    }`}
                  >
                    이 패키지로 신청
                  </Link>
                </div>
              ))}
            </div>
            <p className="mt-6 text-center text-xs text-stone-400">
              표기 가격은 기준안이며 숙소 유형·시즌·물량에 따라 조정됩니다. AI 소재팩·성과 리포트는 옵션으로 추가할 수 있어요.
            </p>
          </div>
        </section>

        {/* Legal / compliance */}
        <section id="legal" className="scroll-mt-20 py-20">
          <div className="mx-auto max-w-4xl px-6">
            <div className="rounded-3xl border border-teal-200 bg-gradient-to-b from-teal-50 to-white p-8 sm:p-12">
              <div className="inline-flex rounded-xl bg-teal-700 p-3 text-white">
                <ShieldCheck />
              </div>
              <h2 className="mt-5 text-2xl font-bold sm:text-3xl">
                체험단 때문에 광고주까지 공정위에 걸리는 시대.
                <br />
                <span className="text-teal-700">우리는 그 리스크를 0으로 만듭니다.</span>
              </h2>
              <p className="mt-4 leading-7 text-stone-600">
                2024~2025년 공정위는 대행사를 직접 제재하기 시작했습니다. 머무는순간의 모든 캠페인은
                다음 SOP를 강제합니다.
              </p>
              <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                {[
                  "실제 1박 체크인 인증 후 촬영",
                  "제목·본문 첫 줄 ‘광고/협찬’ 표기",
                  "미사용·가짜 후기 0건 정책",
                  "9:16 세로형 + 네이버 클립 동시 업로드",
                  "업로드 후 15일 유지",
                  "조회수·도달 데이터 캡처",
                ].map((it) => (
                  <li key={it} className="flex items-start gap-2 rounded-xl bg-white/70 px-4 py-3 text-sm text-stone-700">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
                    <span>{it}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="bg-white py-20">
          <div className="mx-auto max-w-3xl px-6">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">자주 묻는 질문</h2>
            <div className="mt-10 divide-y divide-stone-200 border-y border-stone-200">
              {FAQ.map((f) => (
                <details key={f.q} className="group py-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-semibold text-stone-900">
                    {f.q}
                    <span className="ml-4 text-stone-400 transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 leading-7 text-stone-600">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="px-6 py-20">
          <div className="mx-auto max-w-3xl rounded-3xl bg-stone-900 px-8 py-14 text-center text-white">
            <h2 className="text-2xl font-bold sm:text-3xl">감성 스테이, 제대로 알릴 준비됐나요?</h2>
            <p className="mx-auto mt-3 max-w-md text-stone-300">
              한 지역·한 유형부터, 첫 캠페인은 컨시어지로 직접 챙깁니다.
            </p>
            <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
              <Link
                href="/apply/host"
                className="rounded-full bg-teal-500 px-8 py-3.5 font-semibold text-white transition hover:bg-teal-400"
              >
                숙소 캠페인 신청
              </Link>
              <Link
                href="/apply/creator"
                className="rounded-full border border-white/25 px-8 py-3.5 font-semibold text-white transition hover:bg-white/10"
              >
                크리에이터로 합류
              </Link>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
