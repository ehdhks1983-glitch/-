// lib/ai/analyzePrompt.ts  [업데이트본 — 기획서 4-1 반영]
// 사용자 프롬프트 → 구조화된 사업정보(BizInfo) + "강한 카피에 부족한 정보"(missing)
// 파이프라인 1단계.

import { withFallback, safeParseJson } from "./core";
import type { BizInfo, Lang } from "./types";

const SYSTEM = `너는 랜딩페이지 기획 분석가다.
사용자가 자유롭게 적은 사업/서비스 설명을 읽고, 아래 JSON 스키마로만 정리해 응답한다.
설명·마크다운·코드펜스 없이 JSON 객체 하나만 출력한다.

할 일:
1) 입력을 구조화한다.
2) "강한 카피를 쓰기에 부족한 정보"를 missing 배열에 한국어로 적는다. 다음을 점검한다:
   - 구체적 차별점 (왜 경쟁사 말고 여기인가)
   - 핵심 이득 1~2개 (고객이 실제로 얻는 결과)
   - 신뢰 요소 (경력·사례·보장 등)
   - 타깃의 진짜 고민
   - 가격/혜택 노출 여부
3) 입력에 없는 정보는 지어내지 말고 비우거나 일반화한다.

규칙:
- language는 입력 언어에 맞춰 "ko" 또는 "en".
- tone은 입력에서 드러난 분위기를 간결히 요약(없으면 타깃에 맞게 추정).
- 사실에 근거하고 과장하지 않는다.

스키마:
{
  "service_name": string,
  "target_customer": string,
  "main_problem": string,
  "solution": string,
  "cta": string,
  "tone": string,
  "language": "ko" | "en",
  "missing": string[]
}`;

export async function analyzePrompt(userPrompt: string): Promise<BizInfo> {
  const raw = await withFallback("analyze", { system: SYSTEM, user: userPrompt, json: true });
  const parsed = safeParseJson<Partial<BizInfo>>(raw);

  const lang: Lang = parsed.language === "en" ? "en" : "ko";
  return {
    service_name: str(parsed.service_name),
    target_customer: str(parsed.target_customer),
    main_problem: str(parsed.main_problem),
    solution: str(parsed.solution),
    cta: str(parsed.cta) || (lang === "en" ? "Get started" : "신청하기"),
    tone: str(parsed.tone) || (lang === "en" ? "professional and trustworthy" : "전문적이고 신뢰감 있는"),
    language: lang,
    missing: Array.isArray(parsed.missing) ? parsed.missing.map(str).filter(Boolean).slice(0, 6) : [],
  };
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}
