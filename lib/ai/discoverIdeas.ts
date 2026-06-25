// lib/ai/discoverIdeas.ts  [신규]
// 아이디어 발굴 — 블로그봇 "황금키워드 발굴"의 PromptSite 등가물.
// 시드(업종/주제/타깃) → 랜딩페이지로 만들 만한 "한 줄 프롬프트" 후보 N개 + 근거 + 적합도 점수.
// 발굴 결과의 idea는 기존 생성 파이프라인(analyzePrompt)에 그대로 투입 가능한 한 줄이어야 한다.
//
// 모델 호출은 기존 단일 통로(withFallback) 재사용 → 신규 외부 API/자격증명 0개.
// analyze 체인(비용·속도 우선) 사용. 키 없으면 isMockMode()로 결정적 샘플 반환(core.ts 미수정).

import { withFallback, isMockMode } from "./core";
import type { DiscoveredIdea } from "@/lib/queue/queue";

/** 한 번에 발굴할 최대 아이디어 수(블로그봇의 키워드 다발에 대응). */
export const MAX_IDEAS = 8;
const MAX_SEED = 300;

function buildSystem(count: number): string {
  return `너는 랜딩페이지 기획 전략가다.
사용자가 준 '시드'(업종/주제/타깃 등)를 보고, 그 주변에서 랜딩페이지로 만들 만한
서로 다른 각도의 사업/오퍼 아이디어를 발굴한다.

각 아이디어 규칙:
- idea: PromptSite 생성기에 그대로 넣을 "한 줄 프롬프트"(한국어, 60자 내외).
  누구에게 / 무엇을 / 어떤 행동(CTA)을 받을지가 한 줄에 드러나야 한다.
  예) "30대 직장인 대상 온라인 PT 코칭 랜딩, 무료 상담 신청 받기"
- rationale: 이 각도가 왜 전환에 유리한지 한 줄 근거(고객의 통증/명확한 오퍼).
- fit_score: 0~100 정수. '시드 적합도 + 전환 잠재(수요·구체성·명확한 CTA)'를 추정.
  막연하거나 수요가 불확실하면 낮게, 통증이 뚜렷하고 오퍼가 명확하면 높게.

규칙:
- 정확히 ${count}개. 시드와 무관한 아이디어는 넣지 않는다. 서로 겹치지 않게 각도를 달리한다.
- 지어낸 통계·수치·후기는 절대 넣지 않는다.
- 설명·마크다운·코드펜스 없이 JSON 배열 하나만 출력한다.

스키마: [{ "idea": "", "rationale": "", "fit_score": 0 }]`;
}

/**
 * 시드로 아이디어 후보를 발굴한다(내림차순 정렬, 블로그봇의 "기회점수 내림차순"에 대응).
 * @param seed  시드 키워드/주제(사용자 입력)
 * @param count 발굴 개수(1~MAX_IDEAS)
 */
export async function discoverIdeas(seed: string, count = MAX_IDEAS): Promise<DiscoveredIdea[]> {
  const cleanSeed = seed.trim().slice(0, MAX_SEED);
  const n = Math.max(1, Math.min(MAX_IDEAS, Math.floor(count) || MAX_IDEAS));
  if (!cleanSeed) return [];

  const raw = isMockMode()
    ? JSON.stringify(mockIdeas(cleanSeed, n))
    : await withFallback("analyze", { system: buildSystem(n), user: cleanSeed, json: true });

  let arr: Partial<DiscoveredIdea & { fit_score?: number }>[];
  try {
    arr = safeParseArray(raw);
  } catch {
    return []; // 발굴 실패는 치명적이지 않음 → 빈 결과(라우트에서 안내)
  }

  return arr
    .map((d) => normalizeIdea(d))
    .filter((d): d is DiscoveredIdea => d !== null)
    .sort((a, b) => b.fitScore - a.fitScore)
    .slice(0, n);
}

/** snake_case(fit_score)·camelCase(fitScore) 모두 수용해 안전한 DiscoveredIdea로 정규화. */
function normalizeIdea(d: Partial<DiscoveredIdea & { fit_score?: number }>): DiscoveredIdea | null {
  const idea = typeof d?.idea === "string" ? d.idea.trim() : "";
  if (!idea) return null;
  const rawScore = Number(d?.fitScore ?? d?.fit_score);
  return {
    idea,
    rationale: typeof d?.rationale === "string" ? d.rationale.trim() : "",
    fitScore: Number.isFinite(rawScore) ? Math.max(0, Math.min(100, Math.round(rawScore))) : 0,
  };
}

/** 응답 텍스트에서 JSON 배열만 안전 추출(코드펜스/잡텍스트 방어 — clarifyQuestions 패턴 동일). */
function safeParseArray<T>(text: string): T[] {
  let t = (text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  const a = t.indexOf("[");
  const b = t.lastIndexOf("]");
  if (a !== -1 && b !== -1 && b > a) t = t.slice(a, b + 1);
  const parsed = JSON.parse(t);
  return Array.isArray(parsed) ? (parsed as T[]) : [];
}

/** 키 없는(목) 환경용 결정적 샘플. 시드를 녹여 N개를 만든다(입력과 느슨히 연동). */
function mockIdeas(seed: string, n: number): Array<{ idea: string; rationale: string; fit_score: number }> {
  const angles = [
    { suffix: "무료 상담 신청 받기", why: "낮은 진입장벽 CTA로 리드 확보가 쉬움", score: 82 },
    { suffix: "사전예약·대기자 모집", why: "출시 전 수요 검증과 초기 리스트 확보에 유리", score: 76 },
    { suffix: "무료 체험 후 정기구독 전환", why: "체험으로 가치를 먼저 보여줘 전환률이 높음", score: 79 },
    { suffix: "1:1 맞춤 진단 제공", why: "개인화 오퍼로 신뢰와 전환을 동시에", score: 74 },
    { suffix: "한정 수량 얼리버드 할인", why: "희소성으로 즉시 행동을 유도", score: 71 },
    { suffix: "성공 사례 기반 신뢰 강조", why: "구체적 결과로 망설임을 줄임", score: 68 },
    { suffix: "뉴스레터로 잠재고객 육성", why: "긴 구매주기 상품의 리드 너처링에 적합", score: 64 },
    { suffix: "데모 예약으로 영업 연결", why: "고관여 B2B에서 영업 파이프라인 확보", score: 66 },
  ];
  return angles.slice(0, n).map((a) => ({
    idea: `${seed} — ${a.suffix}`,
    rationale: a.why,
    fit_score: a.score,
  }));
}
