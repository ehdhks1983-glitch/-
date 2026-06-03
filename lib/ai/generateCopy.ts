// lib/ai/generateCopy.ts  [업데이트본 — 기획서 4-3 반영]
// 사업정보(BizInfo)(+보완답변) → 랜딩페이지 섹션별 카피(SectionCopy)
// 파이프라인 2단계. 이 프롬프트가 제품의 핵심 IP("팔리는 카피")다.

import { withFallback, safeParseJson } from "./core";
import type { BizInfo, SectionCopy } from "./types";

function buildSystem(biz: BizInfo): string {
  const ko = biz.language === "ko";
  if (!ko) return buildSystemEn(biz);

  return `너는 전환율로 검증된 다이렉트 리스폰스 카피라이터다. 광고로 트래픽을 받는 랜딩페이지 카피를 쓴다.
아래 사업정보를 바탕으로 섹션별 카피를 JSON 객체 하나로만 출력한다. 설명·마크다운·코드펜스 없이 순수 JSON만.

[팔리는 카피 원칙]
- 구체적으로. 막연한 미사여구 대신 명확한 상황·이득. (입력에 없는 수치·실적·후기는 절대 지어내지 않는다. 숫자가 없으면 '상황의 구체성'으로 대신한다.)
- 기능이 아니라 '나에게 무슨 이득인지'로 번역한다.
- 헤드라인은 10단어 안팎, 핵심 가치 즉시 전달. 낚시·과장 금지.
- 흐름: 문제공감(고객의 언어로 통증 콕 집기) → 해결(우리가 그 다리) → 행동(명확한 CTA 하나).
- FAQ는 진짜 구매 망설임(가격·난이도·위험·"나한테도 될까")을 푼다.
- 사람이 쓴 듯 자연스럽게. 짧은 문장과 리듬. 한 문단 2~3줄.

[금지 — AI 티 나는 상투어]
"오늘날 빠르게 변화하는","혁신적인","게임 체인저","원스톱","차원이 다른","압도적","최고의","완벽한 솔루션","극대화","최적화된 경험". 전부 구체 표현으로 대체.

[좋은 예 (약함 → 강함)]
- 약: "혁신적인 자동화로 업무 효율을 극대화하세요"
  강: "매일 반복하던 엑셀 정리·보고서, 프로그램 하나로 끝내세요"
- 약: "다양한 기능으로 고객 만족을 추구합니다"
  강: "설치하고 바로 쓰세요. 코딩 몰라도 클릭 몇 번이면 작업이 자동으로 돌아갑니다"
- 약(FAQ): "저희 제품은 누구나 쉽게 쓸 수 있습니다"
  강(FAQ): "프로그래밍 몰라도 됩니다. 설치 후 안내대로 클릭 몇 번이면 바로 돌아가요."

[안전 규칙]
- 건강/의료 주제라도 '의사','병원','전문의' 등 의료 전문가 사칭/연상 금지. 개인 경험·객관 사실 위주.
- 허위·과장 효능, 보장 표현("100% 완치") 금지.

[톤] ${biz.tone}
[분량] features.items 3~5개, faq 3~5개. 간결하게.
[출력 전 자가 점검 — 통과해야 출력] 1) 헤드라인에 금지어 없음 2) 기능 아닌 이득 3) 지어낸 숫자 없음 4) 문제→해결→행동 흐름 분명

스키마:
{ "hero":{"headline":"","subheadline":"","cta":""},
  "problem":{"title":"","body":""}, "solution":{"title":"","body":""},
  "features":{"title":"","items":[{"title":"","description":""}]},
  "faq":[{"question":"","answer":""}], "cta":{"headline":"","button":""} }`;
}

function buildSystemEn(biz: BizInfo): string {
  return `You are a conversion-proven direct-response copywriter writing landing pages for paid traffic.
Output ONLY one JSON object — no prose, no markdown, no code fences.

[Principles] Be specific (concrete situations/benefits, never invent numbers/reviews not in the input).
Translate features into benefits. Headline <10 words, instant value, no clickbait.
Flow: agitate the pain (in the customer's words) -> solution -> one clear CTA. FAQ answers real buying hesitations.
Write like a human; short sentences, rhythm.
[Banned clichés] "in today's fast-paced world","revolutionary","game-changer","one-stop","unparalleled","best-in-class","seamless","unlock","elevate","optimize your experience". Replace with concrete wording.
[Safety] No impersonating medical professionals; no false/guarantee claims.
[Tone] ${biz.tone}
[Length] features.items 3-5, faq 3-5. Concise.
Schema:
{ "hero":{"headline":"","subheadline":"","cta":""}, "problem":{"title":"","body":""},
  "solution":{"title":"","body":""}, "features":{"title":"","items":[{"title":"","description":""}]},
  "faq":[{"question":"","answer":""}], "cta":{"headline":"","button":""} }`;
}

function buildUser(biz: BizInfo, extraContext?: string): string {
  const base = JSON.stringify(
    {
      service_name: biz.service_name,
      target_customer: biz.target_customer,
      main_problem: biz.main_problem,
      solution: biz.solution,
      cta: biz.cta,
    },
    null,
    2,
  );
  // 보완질문 답변 등 추가 맥락이 있으면 붙인다 (입력 풍부도 = 품질 1번 레버)
  return extraContext ? `${base}\n\n추가 정보:\n${extraContext}` : base;
}

/**
 * @param biz 구조화된 사업정보
 * @param extraContext 보완질문 답변 등 추가 맥락 (clarifyQuestions의 answersToContext 결과)
 */
export async function generateCopy(biz: BizInfo, extraContext?: string): Promise<SectionCopy> {
  const raw = await withFallback("copy", {
    system: buildSystem(biz),
    user: buildUser(biz, extraContext),
    json: true,
  });

  const c = safeParseJson<Partial<SectionCopy>>(raw);

  return {
    hero: {
      headline: s(c.hero?.headline) || biz.service_name,
      subheadline: s(c.hero?.subheadline) || biz.solution,
      cta: s(c.hero?.cta) || biz.cta,
    },
    problem: { title: s(c.problem?.title), body: s(c.problem?.body) || biz.main_problem },
    solution: { title: s(c.solution?.title), body: s(c.solution?.body) || biz.solution },
    features: {
      title: s(c.features?.title),
      items: Array.isArray(c.features?.items)
        ? c.features!.items.map((i) => ({ title: s(i?.title), description: s(i?.description) })).filter((i) => i.title).slice(0, 5)
        : [],
    },
    faq: Array.isArray(c.faq)
      ? c.faq.map((f) => ({ question: s(f?.question), answer: s(f?.answer) })).filter((f) => f.question).slice(0, 5)
      : [],
    cta: { headline: s(c.cta?.headline) || biz.cta, button: s(c.cta?.button) || biz.cta },
  };
}

function s(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}
