// lib/ai/suggestHeadlines.ts  [신규]
// 헤드라인 후보 — 블로그봇 "키워드당 제목 후보 N개 → 택1 후 글쓰기"의 PromptSite 등가물.
// 한 줄 아이디어 → 서로 다른 각도의 '히어로 헤드라인' 후보 N개. 사용자가 1개 고르면
// 큐 항목에 저장되고, 생성 시 (a) 본문 스티어링 + (b) hero.headline 강제 반영에 쓰인다.
//
// 모델 호출은 기존 단일 통로(withFallback) 재사용 → 신규 자격증명 0개. analyze 체인(저비용).
// 키 없으면 isMockMode()로 결정적 샘플 반환(core.ts 미수정).

import { withFallback, isMockMode } from "./core";

export const MAX_HEADLINES = 3;
const MAX_IDEA = 300;

function buildSystem(n: number): string {
  return `너는 전환율로 검증된 다이렉트 리스폰스 카피라이터다.
아래 한 줄 아이디어로 만들 랜딩페이지의 '히어로 헤드라인' 후보를 ${n}개 제안한다.

규칙:
- 각 후보는 서로 다른 각도(이득 / 통증 / 호기심 / 긴급성 등)로.
- 10단어 안팎, 핵심 가치를 즉시 전달. 낚시·과장 금지.
- 상투어 금지: "혁신적","최고의","압도적","완벽한","게임 체인저","극대화".
- 입력에 없는 수치·실적·후기는 절대 지어내지 않는다.
- 설명·마크다운·코드펜스 없이 JSON 문자열 배열 하나만: ["", "", ""]`;
}

/**
 * 한 줄 아이디어로 히어로 헤드라인 후보를 만든다.
 * @param idea 한 줄 프롬프트(큐 항목의 idea)
 * @param n    후보 수(1~MAX_HEADLINES)
 */
export async function suggestHeadlines(idea: string, n = MAX_HEADLINES): Promise<string[]> {
  const clean = idea.trim().slice(0, MAX_IDEA);
  const count = Math.max(1, Math.min(MAX_HEADLINES, Math.floor(n) || MAX_HEADLINES));
  if (!clean) return [];

  const raw = isMockMode()
    ? JSON.stringify(mockHeadlines(clean, count))
    : await withFallback("analyze", { system: buildSystem(count), user: clean, json: true });

  let arr: unknown[];
  try {
    arr = safeParseArray(raw);
  } catch {
    return [];
  }

  const seen = new Set<string>();
  const out: string[] = [];
  for (const v of arr) {
    const h = typeof v === "string" ? v.trim() : "";
    if (!h) continue;
    const key = h.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(h);
    if (out.length >= count) break;
  }
  return out;
}

/** 응답에서 JSON 배열만 안전 추출(코드펜스/잡텍스트 방어 — discoverIdeas와 동일 패턴). */
function safeParseArray(text: string): unknown[] {
  let t = (text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  const a = t.indexOf("[");
  const b = t.lastIndexOf("]");
  if (a !== -1 && b !== -1 && b > a) t = t.slice(a, b + 1);
  const parsed = JSON.parse(t);
  return Array.isArray(parsed) ? parsed : [];
}

/** 키 없는(목) 환경용 결정적 샘플 헤드라인. 아이디어의 핵심부를 녹여 각도별로 변주. */
function mockHeadlines(idea: string, n: number): string[] {
  const core = idea.split("—")[0].split(/[,·]/)[0].trim() || idea;
  const variants = [
    `${core}, 오늘 바로 시작하세요`, // 이득/행동
    `아직도 ${core} 때문에 망설이시나요?`, // 통증/공감
    `${core} — 3분이면 충분합니다`, // 호기심/간결
  ];
  return variants.slice(0, n);
}
