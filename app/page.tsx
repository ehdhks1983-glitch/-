// app/page.tsx — 머무는순간 · Film Proof 랜딩(광고주 전환 목표).
// 섹션 순서: 히어로 → 신뢰배지 → 문제 → 3스텝 → 증거 → 큐레이션 → 가격 → FAQ → 최종CTA.
import Link from "next/link";
import Nav from "@/components/site/Nav";
import Footer from "@/components/site/Footer";
import ContactCard, { type ContactCardData } from "@/components/site/ContactCard";
import ApplicationForm from "@/components/ApplicationForm";
import { BRAND, PACKAGES } from "@/lib/brand";
import { ShieldCheck, Play, Check } from "@/components/site/icons";

const TONES = [
  "bg-[#20211d]", "bg-[#22201b]", "bg-[#1d2320]", "bg-[#241f1c]",
  "bg-[#1f2126]", "bg-[#232019]", "bg-[#1e221f]", "bg-[#26211e]", "bg-[#202320]",
];

const HERO_CARDS: ContactCardData[] = [
  { region: "제주 · 서귀포", date: "REC 00:14", tone: TONES[0] },
  { region: "강원 · 양양", date: "REC 00:22", tone: TONES[3], stamped: true },
  { region: "가평 · 한옥", date: "REC 00:09", tone: TONES[2] },
];

const EVIDENCE_CARDS: ContactCardData[] = [
  { region: "제주 · 독채", date: "2026.—.—", tone: TONES[0], stamped: true },
  { region: "양양 · 풀빌라", date: "2026.—.—", tone: TONES[1] },
  { region: "가평 · 한옥", date: "2026.—.—", tone: TONES[2] },
  { region: "양평 · 디자인", date: "2026.—.—", tone: TONES[4], stamped: true },
  { region: "속초 · 오션", date: "2026.—.—", tone: TONES[5] },
  { region: "경주 · 풀빌라", date: "2026.—.—", tone: TONES[6] },
];

const BADGES = [
  { icon: ShieldCheck, t: "신고 확인된 스테이만", d: "안전민박 조회 통과 여부 확인" },
  { icon: Check, t: "공정위 표시광고법 100% 준수", d: "제목·본문 첫 줄 ‘광고/협찬’ 표기" },
  { icon: Play, t: "AI 생성 아님 · 실제 1박 인증", d: "실제 체크인 후에만 촬영" },
];

const PROBLEMS = [
  "광고비는 쓰는데 예약은 그대로예요.",
  "체험단 맡겼다가 뒷광고로 걸릴까 봐 불안해요.",
  "블로그 후기는 쌓였는데 숏폼은 어디서 구해야 할지 모르겠어요.",
];

const STEPS = [
  { n: "01", t: "신청", d: "스테이 정보·사진을 제출해요. (약 5분)" },
  { n: "02", t: "큐레이션", d: "4가지 기준으로 심사하고, 통과한 곳만 진행해요." },
  { n: "03", t: "제작 & 배포", d: "실제 1박 체험 후 릴스·클립 업로드 + AI 소재 변형팩까지." },
];

const CRITERIA = [
  { t: "비주얼 완성도", d: "숏폼에 담았을 때 ‘멈추게 되는’ 공간인지." },
  { t: "신고 확인 여부", d: "안전민박 조회로 정식 등록 숙소인지 확인." },
  { t: "사장님 응대 태도", d: "크리에이터와 원활히 협업 가능한지." },
  { t: "합리적 가격", d: "체험 가치에 맞는 정직한 가격인지." },
];

const FAQ = [
  {
    q: "진짜 효과 있나요?",
    a: "숙박은 비주얼 의존도가 가장 높은 업종이라 숏폼이 예약 전환에 직결됩니다. 다만 저희는 아직 베타 단계라, 과장된 수치를 약속하지 않습니다. 대신 실제 1박 인증 기반의 진짜 콘텐츠와 AI 소재 변형팩으로 노출 물량을 함께 확보합니다. 첫 캠페인 성과 데이터가 쌓이면 이 자리를 실제 숫자로 교체합니다.",
  },
  {
    q: "크몽보다 비싸 보이는데요?",
    a: "건당 몇만 원짜리 프리랜서와는 지향점이 다릅니다. 저희는 ‘큐레이션 + 공정위 합법 + 실제 1박 + AI 소재팩’을 묶어 제공합니다. OTA 평균 수수료(15%)와 달리 1회성 비용이며, 뒷광고 리스크를 0으로 만드는 값이 포함되어 있습니다.",
  },
  {
    q: "우리 숙소도 신청할 수 있나요?",
    a: "감성 독채 펜션·풀빌라·한옥스테이·디자인 스테이 등 비주얼이 강한 스테이를 우선합니다. 모텔·비즈니스호텔·대형 리조트는 받지 않습니다. 신청한다고 모두 진행하지 않으며, 4가지 큐레이션 기준을 통과한 곳만 진행합니다.",
  },
  {
    q: "뭘 준비해야 하나요?",
    a: "스테이 정보와 사진 몇 장이면 신청은 5분이면 끝납니다. 선정되면 1박 체험 일정을 조율하고, 콘텐츠 방향은 저희가 크리에이터와 함께 잡아드립니다.",
  },
  {
    q: "계약·정산·환불은 어떻게 되나요?",
    a: "캠페인 전 서면으로 범위·일정·비용·환불 조건을 명시하고, 표시광고법 준수를 약정서에 담습니다. 정산 방식과 환불 정책은 계약서에 명확히 안내드립니다. (베타 기간 조건은 별도 안내)",
  },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-ink text-paper">
      <Nav />

      <main className="flex-1">
        {/* 1) 히어로 */}
        <section className="relative overflow-hidden border-b border-line">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_70%_0%,rgba(232,93,44,0.10),transparent)]" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-5 py-16 lg:grid-cols-[1.1fr_1fr] lg:py-24">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.2em] text-film">
                {BRAND.name} — 실제 방문 인증 숏폼 체험단
              </p>
              <h1 className="headline mt-5 font-sans text-5xl text-paper sm:text-6xl lg:text-7xl">
                가짜 후기 말고,
                <br />
                진짜 <span className="text-film">하룻밤.</span>
              </h1>
              <p className="mt-6 max-w-md font-serif text-lg leading-8 text-paper-dim">
                공정위 100% 합법 · 신고 확인된 스테이만 · AI가 아닌 실제 1박 체크인 인증.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/#apply"
                  className="rounded-full bg-film px-7 py-3.5 text-center text-base font-bold text-on-orange shadow-lg shadow-film/20 transition hover:brightness-110"
                >
                  무료로 캠페인 만들기
                </Link>
                <Link
                  href="/apply/creator"
                  className="rounded-full border border-line px-7 py-3.5 text-center text-base font-semibold text-paper transition hover:border-paper/40"
                >
                  크리에이터로 참여하기
                </Link>
              </div>
              <p className="mt-4 font-mono text-xs text-muted">베타 오픈 · {BRAND.defaultRegionNote}</p>
            </div>

            {/* 필름 콘택트시트 프리뷰 */}
            <div className="relative mx-auto flex max-w-sm items-center justify-center gap-3 sm:gap-4">
              <ContactCard data={HERO_CARDS[0]} tilt="tilt-l" className="w-1/3 translate-y-4" />
              <ContactCard data={HERO_CARDS[1]} tilt="tilt-r" className="z-10 w-2/5 -translate-y-2 shadow-2xl" />
              <ContactCard data={HERO_CARDS[2]} tilt="tilt-0" className="w-1/3 translate-y-6" />
            </div>
          </div>
        </section>

        {/* 2) 신뢰 배지 바 */}
        <section className="border-b border-line bg-[#17181d]">
          <div className="mx-auto grid max-w-5xl gap-px px-5 py-8 sm:grid-cols-3">
            {BADGES.map((b) => (
              <div key={b.t} className="flex items-start gap-3 px-2 py-2">
                <span className="mt-0.5 shrink-0 text-sage">
                  <b.icon className="h-6 w-6" />
                </span>
                <div>
                  <p className="text-sm font-bold text-paper">{b.t}</p>
                  <p className="mt-0.5 font-serif text-xs text-muted">{b.d}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 3) 문제 장면 */}
        <section className="mx-auto max-w-6xl px-5 py-20">
          <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">이런 고민, 다 압니다</h2>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {PROBLEMS.map((p, i) => (
              <div key={p} className="rounded-xl border border-line bg-[#191a1f] p-6">
                <span className="font-mono text-sm text-film">0{i + 1}</span>
                <p className="mt-3 font-serif text-lg leading-7 text-paper-dim">“{p}”</p>
              </div>
            ))}
          </div>
        </section>

        {/* 4) 3스텝 */}
        <section id="how" className="scroll-mt-20 border-y border-line bg-[#17181d] py-20">
          <div className="mx-auto max-w-6xl px-5">
            <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">번거로울까 봐요? 3단계면 끝납니다</h2>
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {STEPS.map((s) => (
                <div key={s.n} className="relative rounded-2xl border border-line bg-ink p-7">
                  <span className="font-mono text-4xl font-bold text-film/80">{s.n}</span>
                  <h3 className="mt-4 text-xl font-bold text-paper">{s.t}</h3>
                  <p className="mt-2 font-serif leading-7 text-paper-dim">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* 5) 증거 쇼케이스 */}
        <section id="evidence" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20">
          <div className="max-w-2xl">
            <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">숫자보다, 증거를 보여드립니다</h2>
            <p className="mt-4 font-serif text-lg leading-8 text-paper-dim">
              캠페인마다 실제 체크인 인증을 남깁니다. AI로 만든 장면이 아니라,
              <span className="text-paper"> 실제로 그 자리에 있었다는 증거</span>입니다.
            </p>
            <p className="mt-2 font-mono text-xs text-muted">
              * 아래는 콘텐츠가 들어갈 자리입니다. 첫 캠페인이 쌓이면 실제 인증 영상으로 교체됩니다. (스톡사진·가짜 후기 미사용)
            </p>
          </div>
          <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-6">
            {EVIDENCE_CARDS.map((c, i) => (
              <ContactCard key={i} data={c} tilt={i % 2 === 0 ? "tilt-0" : ""} />
            ))}
          </div>
        </section>

        {/* 6) 큐레이션 기준 */}
        <section className="border-y border-line bg-[#17181d] py-20">
          <div className="mx-auto max-w-6xl px-5">
            <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">아무 숙소나 받지 않습니다</h2>
            <p className="mt-4 max-w-xl font-serif text-lg leading-8 text-paper-dim">
              신청한다고 다 진행하지 않아요. 다음 4가지 기준을 통과한 스테이만 캠페인으로 만듭니다.
            </p>
            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {CRITERIA.map((c, i) => (
                <div key={c.t} className="rounded-2xl border border-line bg-ink p-6">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full border border-sage/50 font-mono text-sm font-bold text-sage">
                    {i + 1}
                  </div>
                  <h3 className="mt-4 font-bold text-paper">{c.t}</h3>
                  <p className="mt-2 font-serif text-sm leading-6 text-paper-dim">{c.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* 7) 가격 */}
        <section id="pricing" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20">
          <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">가격</h2>
          <p className="mt-4 font-serif text-lg text-paper-dim">
            큐레이션 + 합법 + 실제 1박 + AI 소재팩. 현물 1박은 광고주 제공, 대행료는 아래 기준입니다.
          </p>
          <div className="mt-12 grid gap-5 lg:grid-cols-3">
            {PACKAGES.map((p) => (
              <div
                key={p.id}
                className={`relative rounded-2xl border p-7 ${
                  p.featured ? "border-film bg-[#211712]" : "border-line bg-[#191a1f]"
                }`}
              >
                {p.featured && (
                  <span className="absolute -top-3 left-7 rounded-full bg-film px-3 py-1 font-mono text-xs font-bold text-on-orange">
                    추천
                  </span>
                )}
                <h3 className="text-lg font-bold text-paper">{p.name}</h3>
                <p className="mt-1 font-mono text-xs uppercase tracking-wider text-muted">{p.summary}</p>
                <p className="mt-4 text-2xl font-black text-paper">{p.price}</p>
                <ul className="mt-5 space-y-2.5">
                  {p.items.map((it) => (
                    <li key={it} className="flex items-start gap-2 font-serif text-sm text-paper-dim">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
                      <span>{it}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href="/#apply"
                  className={`mt-7 block rounded-xl px-5 py-3 text-center text-sm font-bold transition ${
                    p.featured
                      ? "bg-film text-on-orange hover:brightness-110"
                      : "border border-line text-paper hover:border-paper/40"
                  }`}
                >
                  이 구성으로 신청
                </Link>
              </div>
            ))}
          </div>
          <p className="mt-6 font-mono text-xs text-muted">
            * OTA 평균 수수료 15%보다 낮고, 1회성입니다. 표기 가격은 기준안이며 유형·시즌·물량에 따라 조정됩니다.
          </p>
        </section>

        {/* 8) FAQ */}
        <section id="faq" className="scroll-mt-20 border-y border-line bg-[#17181d] py-20">
          <div className="mx-auto max-w-3xl px-5">
            <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">자주 묻는 질문</h2>
            <div className="mt-10 divide-y divide-line border-y border-line">
              {FAQ.map((f) => (
                <details key={f.q} className="group py-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-bold text-paper">
                    {f.q}
                    <span className="ml-4 text-film transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 font-serif leading-7 text-paper-dim">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* 9) 최종 CTA (듀얼) + 광고주 신청 폼 */}
        <section id="apply" className="scroll-mt-20 py-20">
          <div className="mx-auto max-w-6xl px-5">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.1fr]">
              <div>
                <h2 className="headline font-sans text-3xl text-paper sm:text-4xl">
                  진짜 하룻밤으로,
                  <br />
                  예약을 만들 시간
                </h2>
                <p className="mt-5 font-serif text-lg leading-8 text-paper-dim">
                  베타 기간 동안 첫 캠페인은 컨시어지로 직접 챙깁니다. 5분이면 신청이 끝나요.
                </p>
                <div className="mt-8 rounded-2xl border border-line bg-[#191a1f] p-5">
                  <p className="font-mono text-xs uppercase tracking-wider text-muted">크리에이터신가요?</p>
                  <p className="mt-2 font-serif text-paper-dim">
                    여행·감성 라이프스타일 숏폼 크리에이터를 모십니다. 실제 1박 후 촬영하는 합법 캠페인이에요.
                  </p>
                  <Link
                    href="/apply/creator"
                    className="mt-4 inline-block rounded-full border border-line px-5 py-2.5 text-sm font-semibold text-paper transition hover:border-paper/40"
                  >
                    숏폼 크리에이터로 참여하기
                  </Link>
                </div>
              </div>

              <div className="rounded-2xl border border-line bg-paper p-6 text-ink sm:p-8">
                <h3 className="text-xl font-black tracking-tight text-ink">무료로 캠페인 만들기</h3>
                <p className="mt-1.5 font-serif text-sm text-ink/60">
                  큐레이션 심사 후 영업일 2~3일 내 연락드려요. (베타 오픈)
                </p>
                <div className="mt-6">
                  <ApplicationForm kind="host" />
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
