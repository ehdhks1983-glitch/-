// lib/ai/clarifyQuestions.ts  [신규 — 기획서 4-2]
// 입력 풍부도(품질 1번 레버)를 끌어올리는 모듈.
// analyzePrompt가 채운 missing[]을 사용자가 1분 안에 답할 수 있는 짧은 질문으로 바꾼다.

import { withFallback } from "./core";
import type { BizInfo } from "./types";

export interface ClarifyQuestion {
  question: string;
  options: string[]; // 객관식 보기 (없으면 빈 배열 → 단답)
}

export interface ClarifyAnswer {
  question: string;
  answer: string;
}

const SYSTEM = `아래 missing(부족 정보) 항목들을, 사용자가 1분 안에 답할 수 있는 짧은 질문 최대 3개로 바꿔라.
- 한 질문은 한 가지만 묻는다.
- 가능하면 객관식 보기 2~4개를 함께 제시한다(예: "가격을 표시할까요?" → ["표시","출시 예정 표기","비공개"]).
- 설명·마크다운 없이 JSON 배열로만 출력한다: [{ "question": "", "options": ["",""] }]`;

export async function clarifyQuestions(biz: BizInfo): Promise<ClarifyQuestion[]> {
  if (!biz.missing?.length) return [];

  const user = JSON.stringify({
    missing: biz.missing,
    service_name: biz.service_name,
    target_customer: biz.target_customer,
  });

  const raw = await withFallback("analyze", { system: SYSTEM, user, json: true });

  // 4-2는 배열을 반환 → 배열 안전 파싱 (코드펜스/잡텍스트 방어)
  let arr: Partial<ClarifyQuestion>[] = [];
  try {
    arr = safeParseArray<Partial<ClarifyQuestion>>(raw);
  } catch {
    return []; // 보완질문은 실패해도 치명적이지 않음 → 그냥 건너뛰고 바로 카피 생성
  }

  return arr
    .map((q) => ({
      question: str(q.question),
      options: Array.isArray(q.options) ? q.options.map(str).filter(Boolean).slice(0, 4) : [],
    }))
    .filter((q) => q.question)
    .slice(0, 3);
}

/** 사용자 답변을 generateCopy(biz, extraContext)에 넣을 맥락 문자열로 변환 */
export function answersToContext(answers: ClarifyAnswer[]): string {
  return answers
    .filter((a) => a.answer && a.answer.trim())
    .map((a) => `- ${a.question} → ${a.answer.trim()}`)
    .join("\n");
}

/** 응답 텍스트에서 JSON 배열만 안전 추출 */
function safeParseArray<T>(text: string): T[] {
  let t = (text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  const a = t.indexOf("[");
  const b = t.lastIndexOf("]");
  if (a !== -1 && b !== -1 && b > a) t = t.slice(a, b + 1);
  const parsed = JSON.parse(t);
  return Array.isArray(parsed) ? (parsed as T[]) : [];
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}
