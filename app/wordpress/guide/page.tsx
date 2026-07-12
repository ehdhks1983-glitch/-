// app/wordpress/guide/page.tsx  [신규 — 워드프레스 자동 발행]
// 워드프레스 입문 가이드 — 네이버 블로그만 써본 초보자에게 구조와 자동 발행 원리를 설명한다.
// 정적 콘텐츠라 서버 컴포넌트로 충분하다.

import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "워드프레스 입문 가이드 — PromptSite",
  description:
    "네이버 블로그와 비교로 이해하는 워드프레스 구조, 그리고 자동 발행이 안전하게 동작하는 원리.",
};

const COMPARE_ROWS: [string, string, string][] = [
  ["시작 방법", "네이버 가입만 하면 끝", "호스팅 계약 + 워드프레스 설치(자동 설치 지원)"],
  ["비용", "무료", "호스팅 월 5천~2만원 + 도메인 연 1~2만원"],
  ["소유권", "네이버 소유 (규칙·노출 모두 네이버 결정)", "100% 내 것 (글·디자인·데이터 전부)"],
  ["자동 발행", "공식 지원 없음 → 봇은 편법(정지 위험)", "공식 문(REST API) 제공 → 안전한 자동화"],
  ["수익화", "애드포스트(수익 제한적)", "구글 애드센스·제휴·광고 자유 배치"],
  ["검색 유입", "네이버 검색 위주", "구글 검색 위주 (전 세계 대상)"],
];

const PARTS = [
  {
    icon: "🏠",
    name: "호스팅 (서버)",
    desc: "내 블로그가 살아 있는 컴퓨터를 빌리는 것. 카페24·가비아·닷홈(국내), Cloudways(해외) 등에서 월 5천원~. “워드프레스 자동 설치”를 지원하는 곳을 고르면 클릭 몇 번으로 끝나요.",
  },
  {
    icon: "📍",
    name: "도메인 (주소)",
    desc: "myblog.com 같은 인터넷 주소. 연 1~2만원이며 보통 호스팅 가입할 때 같이 삽니다. 자동화 연결에는 https(보안 자물쇠)가 필요한데, 요즘 호스팅은 무료로 켜줍니다.",
  },
  {
    icon: "⚙️",
    name: "워드프레스 (프로그램)",
    desc: "글쓰기·관리를 담당하는 소프트웨어 자체. 완전 무료(오픈소스)이고 호스팅에 설치해서 씁니다. 설치가 끝나면 “내주소/wp-admin”이 네이버 블로그 관리 페이지 같은 관리자 화면이 돼요.",
  },
];

const FLOW = [
  { n: "1", title: "이 프로그램에서 글 준비", desc: "키워드로 AI 초안 생성, 카테고리·발행 시각 지정" },
  { n: "2", title: "열쇠로 공식 문 통과", desc: "응용 프로그램 비밀번호(전용 열쇠)로 REST API에 인증" },
  { n: "3", title: "내 워드프레스에 등록", desc: "즉시 발행 또는 예약 상태로 안전하게 저장" },
  { n: "4", title: "워드프레스가 알아서 발행", desc: "예약 시각이 되면 사이트가 스스로 공개 — 프로그램을 꺼도 OK" },
];

const STEPS = [
  ["호스팅 가입 + 워드프레스 자동 설치", "약 10분. 결제하면 “워드프레스 설치” 버튼이 있어요. 아이디/비밀번호만 정하면 설치 완료."],
  ["도메인 연결 + https 켜기", "호스팅 관리 화면에서 도메인을 연결하고 무료 SSL(https)을 켭니다. 대부분 버튼 하나예요."],
  ["관리자 화면 접속", "브라우저에서 “내주소/wp-admin” 접속 → 설치 때 만든 계정으로 로그인."],
  ["프로그램용 열쇠 발급", "사용자 → 프로필 → 응용 프로그램 비밀번호에서 이름을 넣고 [추가] → 24자리 열쇠 복사."],
  ["이 프로그램과 연결", "[연결 설정]에 사이트 주소·아이디·열쇠 입력 → 카테고리 만들고 자동 발행 시작!"],
];

const FAQS = [
  {
    q: "돈이 얼마나 들어요?",
    a: "워드프레스 자체는 무료입니다. 실제 비용은 호스팅(월 5천~2만원)과 도메인(연 1~2만원)뿐이에요. 커피 두 잔 값으로 내 소유의 블로그가 생기는 셈입니다.",
  },
  {
    q: "코딩을 알아야 하나요?",
    a: "아니요. 설치는 호스팅 업체의 자동 설치가, 글 발행은 이 프로그램이 대신합니다. 관리자 화면도 네이버 블로그 관리 페이지처럼 클릭으로 조작해요.",
  },
  {
    q: "가입형(wordpress.com)과 설치형(wordpress.org)이 있다던데요?",
    a: "이 프로그램은 호스팅에 설치하는 “설치형” 기준입니다. 가입형(wordpress.com)의 무료·저가 요금제는 외부 프로그램 연결(응용 프로그램 비밀번호)이 막혀 있어요. 호스팅 자동 설치를 이용하면 자연스럽게 설치형입니다.",
  },
  {
    q: "네이버 블로그는 그만둬야 하나요?",
    a: "아니요, 둘 다 운영하는 분이 많습니다. 네이버는 국내 검색 유입, 워드프레스는 구글 유입과 애드센스 수익 담당 — 역할이 달라요. 이 프로그램으로 워드프레스 쪽 글은 자동으로 쌓으면 됩니다.",
  },
  {
    q: "네이버처럼 저품질에 걸리진 않나요?",
    a: "내 사이트라 네이버식 “저품질 블로그” 개념 자체가 없습니다. 다만 구글도 복붙·도배 글은 노출을 안 시켜주니, 이 프로그램의 AI 초안을 검토·수정해서 올리는 습관이 좋아요.",
  },
];

export default function WpGuidePage() {
  return (
    <div className="mx-auto max-w-3xl">
      {/* 헤더 */}
      <div className="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 p-8 text-white">
        <span className="inline-block rounded-full border border-white/40 bg-white/15 px-3 py-1 text-xs font-semibold">
          입문 가이드
        </span>
        <h1 className="mt-3 text-2xl font-bold sm:text-3xl">
          워드프레스, 처음이신가요?
        </h1>
        <p className="mt-2 text-sm leading-6 text-indigo-100">
          네이버 블로그와 비교하면 쉽습니다. 5분만 읽으면 구조가 보여요.
        </p>
      </div>

      {/* 1. 네이버와 비교 */}
      <section className="mt-8">
        <h2 className="text-xl font-bold">1. 네이버 블로그와 뭐가 다른가요?</h2>
        <p className="mt-3 text-sm leading-7 text-slate-600">
          <strong>네이버 블로그</strong>는 네이버가 지은 건물에 <strong>세 들어 사는 것</strong>
          이에요. 가입만 하면 바로 쓰지만, 건물 규칙(노출·저품질·수익)은 전부 네이버가 정합니다.{" "}
          <strong>워드프레스</strong>는 <strong>내 땅에 지은 내 집</strong>입니다. 처음에 집을
          마련하는 과정(호스팅)이 필요하지만, 그 후엔 디자인·광고·데이터 전부 내 마음대로이고
          글이 쌓일수록 내 자산이 됩니다.
        </p>
        <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left">
                <th className="px-4 py-3 font-semibold"> </th>
                <th className="px-4 py-3 font-semibold text-emerald-700">네이버 블로그</th>
                <th className="px-4 py-3 font-semibold text-indigo-700">워드프레스</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map(([label, naver, wp]) => (
                <tr key={label} className="border-b border-slate-100 last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-700">{label}</td>
                  <td className="px-4 py-3 text-slate-600">{naver}</td>
                  <td className="px-4 py-3 text-slate-600">{wp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 2. 구조 */}
      <section className="mt-10">
        <h2 className="text-xl font-bold">2. 워드프레스는 딱 3가지 조합이에요</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {PARTS.map((p) => (
            <div key={p.name} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="text-2xl">{p.icon}</div>
              <h3 className="mt-2 font-semibold">{p.name}</h3>
              <p className="mt-1.5 text-xs leading-5 text-slate-500">{p.desc}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 rounded-xl bg-slate-100 px-4 py-3 text-sm leading-6 text-slate-600">
          🧭 정리: <strong>호스팅(땅과 건물) + 도메인(주소) + 워드프레스(집 관리 프로그램)</strong>.
          호스팅 업체의 &ldquo;워드프레스 자동 설치&rdquo;를 쓰면 세 가지가 한 번에 준비됩니다.
        </p>
      </section>

      {/* 3. 자동 발행 원리 */}
      <section className="mt-10">
        <h2 className="text-xl font-bold">3. 자동 발행은 어떤 원리인가요?</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-red-100 bg-red-50/60 p-5">
            <h3 className="text-sm font-bold text-red-700">네이버 자동화봇 방식</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              네이버에는 자동화 프로그램용 공식 문이 <strong>없습니다</strong>. 그래서 봇이{" "}
              <strong>사람인 척 로그인해서 화면을 클릭</strong>하는 편법을 씁니다. 네이버가
              감지하면 저품질·계정 정지 위험이 있는 이유예요.
            </p>
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-5">
            <h3 className="text-sm font-bold text-emerald-700">워드프레스 방식 (이 프로그램)</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              워드프레스에는 <strong>REST API라는 공식 출입문</strong>이 처음부터 있습니다.
              프로그램 전용 열쇠(응용 프로그램 비밀번호)를 발급받아 정문으로 들어가는 구조라{" "}
              <strong>정지 위험 없이</strong> 자동 발행이 됩니다.
            </p>
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-6">
          <h3 className="text-sm font-semibold text-slate-500">자동 발행 흐름</h3>
          <ol className="mt-4 space-y-3">
            {FLOW.map((f) => (
              <li key={f.n} className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                  {f.n}
                </span>
                <div>
                  <p className="text-sm font-semibold">{f.title}</p>
                  <p className="text-xs leading-5 text-slate-500">{f.desc}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-4 rounded-xl bg-indigo-50 px-4 py-3 text-xs leading-5 text-indigo-800">
            🔑 열쇠(응용 프로그램 비밀번호)는 로그인 비밀번호와 별개라서, 프로필에서{" "}
            <strong>철회</strong> 버튼 한 번이면 즉시 무효화됩니다. 열쇠는 이 브라우저에만
            저장되고 저희 서버에는 저장되지 않아요.
          </p>
        </div>
      </section>

      {/* 4. 시작 5단계 */}
      <section className="mt-10">
        <h2 className="text-xl font-bold">4. 0에서 첫 자동 발행까지 — 5단계</h2>
        <ol className="mt-4 space-y-3">
          {STEPS.map(([title, desc], i) => (
            <li key={title} className="flex gap-4 rounded-2xl border border-slate-200 bg-white p-5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-bold text-white">
                {i + 1}
              </span>
              <div>
                <p className="font-semibold">{title}</p>
                <p className="mt-1 text-sm leading-6 text-slate-500">{desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* 5. FAQ */}
      <section className="mt-10">
        <h2 className="text-xl font-bold">5. 자주 묻는 질문</h2>
        <div className="mt-4 space-y-3">
          {FAQS.map((f) => (
            <details key={f.q} className="group rounded-2xl border border-slate-200 bg-white p-5">
              <summary className="cursor-pointer list-none font-semibold marker:hidden">
                <span className="mr-2 text-indigo-600">Q.</span>
                {f.q}
              </summary>
              <p className="mt-3 text-sm leading-7 text-slate-600">{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* CTA */}
      <div className="mt-10 rounded-2xl border border-indigo-100 bg-indigo-50/70 p-8 text-center">
        <h2 className="text-lg font-bold">이제 구조가 보이시죠?</h2>
        <p className="mt-2 text-sm text-slate-600">
          워드프레스가 준비됐다면 1분이면 연결됩니다. 발급 방법은 연결 화면에도 안내되어 있어요.
        </p>
        <Link
          href="/wordpress"
          className="mt-5 inline-block rounded-full bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:bg-indigo-500"
        >
          연결하러 가기 →
        </Link>
      </div>
    </div>
  );
}
