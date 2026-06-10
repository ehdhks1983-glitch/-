// scripts/build-demo.tsx
// 실제 템플릿 컴포넌트를 목 카피로 정적 렌더 → 단일 HTML(탭으로 3종 전환)로 출력.
// 키/서버 없이 디자인을 브라우저에서 바로 확인하기 위한 데모 생성기.
// 실행: npm run demo   (출력: promptsite-demo.html)

import { renderToStaticMarkup } from "react-dom/server";
import { writeFileSync } from "node:fs";
import React from "react";
import TemplateRenderer from "../components/templates/TemplateRenderer";
import type { BizInfo, SectionCopy, TemplateId } from "../lib/ai/types";

const biz: BizInfo = {
  service_name: "핏코치",
  target_customer: "운동을 시작하려는 30대 직장인",
  main_problem: "퇴근 후 시간이 없고 혼자서는 작심삼일로 끝난다",
  solution: "주 3회 1:1 화상 PT 코칭과 식단 피드백으로 꾸준함을 만든다",
  cta: "무료 상담 신청하기",
  tone: "친근하고 신뢰감 있는",
  language: "ko",
  missing: [],
};

const copy: SectionCopy = {
  hero: {
    headline: "퇴근 후 30분, 작심삼일을 끝냅니다",
    subheadline: "주 3회 1:1 화상 코칭과 식단 피드백으로 혼자서 못 지키던 운동을 습관으로 만듭니다.",
    cta: "무료 상담 신청하기",
  },
  problem: {
    title: "혼자서는 늘 작심삼일이었죠",
    body: "야근에 치이고, 헬스장은 끊어도 안 가게 되고, 유튜브만 보다 끝나는 밤. 의지가 약해서가 아니라 혼자라서 그렇습니다.",
  },
  solution: {
    title: "옆에서 같이 끌어주는 코치",
    body: "매주 정해진 시간에 화상으로 만나 자세를 잡고, 그날 먹은 걸 사진으로 보내면 피드백이 옵니다. 빠질 수 없는 구조를 만듭니다.",
  },
  features: {
    title: "이렇게 도와드립니다",
    items: [
      { title: "주 3회 1:1 화상 코칭", description: "정해진 시간에 얼굴 보고 운동하니 빠지기 어렵습니다." },
      { title: "식단 사진 피드백", description: "거창한 식단표 대신, 그날 먹은 걸 보내면 바로 코멘트해 드립니다." },
      { title: "직장인 시간대 운영", description: "이른 아침과 늦은 저녁, 퇴근 후에도 시간을 맞출 수 있습니다." },
    ],
  },
  faq: [
    { question: "운동을 한 번도 안 해봤는데 괜찮을까요?", answer: "오히려 그런 분들이 많습니다. 첫 주는 기본 자세부터 천천히 시작합니다." },
    { question: "집에 기구가 없어도 되나요?", answer: "맨몸 운동 위주로 구성하고, 필요하면 저렴한 도구만 안내해 드립니다." },
    { question: "비용이 부담되면요?", answer: "무료 상담에서 목표와 예산을 먼저 듣고 맞는 방식을 함께 정합니다." },
  ],
  cta: { headline: "이번엔 진짜 바꿔봅시다", button: "무료 상담 신청하기" },
};

// 공개 페이지의 신청 섹션과 동일한 모양(데모라 동작은 안 함)
const signupSlot = (
  <section id="signup" className="bg-slate-900 px-6 py-20 text-center">
    <h2 className="text-2xl font-bold text-white sm:text-3xl">{copy.cta.headline}</h2>
    <p className="mt-3 text-slate-300">이메일을 남기면 가장 먼저 알려드릴게요.</p>
    <div className="mx-auto mt-8 flex max-w-md flex-col gap-3 sm:flex-row">
      <input
        placeholder="이메일 주소"
        className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none"
        readOnly
      />
      <span className="cursor-default rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white">
        {copy.cta.button}
      </span>
    </div>
  </section>
);

const templates: { id: TemplateId; name: string }[] = [
  { id: "saas-launch", name: "SaaS Launch" },
  { id: "waitlist", name: "Waitlist" },
  { id: "agency", name: "Agency" },
];

const rendered = templates.map((t) => ({
  ...t,
  html: renderToStaticMarkup(
    React.createElement(TemplateRenderer, { templateId: t.id, copy, lang: "ko" as const, biz, signupSlot }),
  ),
}));

const tabs = rendered
  .map(
    (t, i) =>
      `<button data-tab="${t.id}" class="tab px-4 py-1.5 rounded-full text-sm font-medium ${
        i === 0 ? "bg-indigo-600 text-white" : "bg-white text-slate-600 border border-slate-200"
      }">${t.name}</button>`,
  )
  .join("");

const panels = rendered
  .map((t, i) => `<div data-panel="${t.id}"${i === 0 ? "" : ' style="display:none"'}>${t.html}</div>`)
  .join("\n");

const doc = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>PromptSite 템플릿 미리보기</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
@keyframes fade-up { from { opacity:0; transform:translateY(14px) } to { opacity:1; transform:none } }
.animate-fade-up { animation: fade-up .6s ease-out both }
.animate-fade-up-delay-1 { animation: fade-up .6s .12s ease-out both }
.animate-fade-up-delay-2 { animation: fade-up .6s .24s ease-out both }
</style>
</head>
<body class="bg-slate-100">
<div class="sticky top-0 z-50 flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur">
  <span class="font-bold">Prompt<span class="text-indigo-600">Site</span> 미리보기</span>
  <div class="flex gap-2">${tabs}</div>
  <span class="ml-auto text-xs text-slate-400">목 데이터(핏코치) 렌더 · 업종 테마 자동 적용 · 버튼은 데모라 동작 안 함</span>
</div>
${panels}
<script>
  const btns = document.querySelectorAll('[data-tab]');
  const panels = document.querySelectorAll('[data-panel]');
  btns.forEach((b) => b.addEventListener('click', () => {
    const id = b.getAttribute('data-tab');
    panels.forEach((p) => { p.style.display = p.getAttribute('data-panel') === id ? '' : 'none'; });
    btns.forEach((x) => {
      const on = x.getAttribute('data-tab') === id;
      x.className = 'tab px-4 py-1.5 rounded-full text-sm font-medium ' + (on ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 border border-slate-200');
    });
    window.scrollTo(0, 0);
  }));
</script>
</body>
</html>`;

writeFileSync("promptsite-demo.html", doc, "utf8");
console.log("✓ promptsite-demo.html 생성 완료 (" + doc.length + " bytes)");
