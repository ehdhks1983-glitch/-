// app/api/generate/route.ts  [신규]
// analyze → (clarify) → copy 파이프라인을 묶는 엔드포인트.
// 2단계 흐름:
//   1) { prompt } 만 보내면 → 분석 후 보완질문이 있으면 질문 반환(stage:"clarify")
//   2) { biz, answers } 또는 { biz, skipClarify } 보내면 → 카피 반환(stage:"done")
// AI 에러는 사용자 친화 메시지로만 응답한다(코드·모델 정보 노출 금지).

import { NextResponse } from "next/server";
import { analyzePrompt } from "@/lib/ai/analyzePrompt";
import { clarifyQuestions, answersToContext, type ClarifyAnswer } from "@/lib/ai/clarifyQuestions";
import { generateCopy } from "@/lib/ai/generateCopy";
import { selectTemplate } from "@/lib/ai/selectTemplate";
import type { BizInfo } from "@/lib/ai/types";

export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_PROMPT = 2000;

export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return bad("요청 형식이 올바르지 않습니다.");
  }

  const promptRaw = body.prompt;
  const bizIn = body.biz;
  const hasBiz = isBizInfo(bizIn);

  // 입력 검증(서버단)
  if (!hasBiz) {
    if (typeof promptRaw !== "string" || !promptRaw.trim()) {
      return bad("무엇을 만들지 한 줄로 적어 주세요.");
    }
    if (promptRaw.length > MAX_PROMPT) {
      return bad(`설명이 너무 깁니다. ${MAX_PROMPT}자 이하로 줄여 주세요.`);
    }
  }

  try {
    const biz: BizInfo = hasBiz ? bizIn : await analyzePrompt((promptRaw as string).trim());
    const template = selectTemplate(biz);

    const answers = normalizeAnswers(body.answers);
    const skipClarify = body.skipClarify === true;

    // 1단계: prompt만 들어왔고, 부족 정보가 있으며, 아직 답변이 없으면 보완질문 반환
    const wantClarify = !hasBiz && !skipClarify && biz.missing.length > 0 && answers.length === 0;
    if (wantClarify) {
      const questions = await clarifyQuestions(biz);
      if (questions.length > 0) {
        return NextResponse.json({ stage: "clarify", biz, template, questions });
      }
    }

    // 2단계: 카피 생성
    const extra = answers.length ? answersToContext(answers) : undefined;
    const copy = await generateCopy(biz, extra);
    return NextResponse.json({ stage: "done", biz, template, copy });
  } catch (err) {
    console.error("[api/generate] 실패:", err);
    return NextResponse.json(
      { error: "생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}

function bad(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

/** 클라이언트가 보낸 답변 배열을 안전하게 정규화. */
function normalizeAnswers(input: unknown): ClarifyAnswer[] {
  if (!Array.isArray(input)) return [];
  const out: ClarifyAnswer[] = [];
  for (const item of input) {
    if (item && typeof item === "object") {
      const r = item as Record<string, unknown>;
      const question = typeof r.question === "string" ? r.question : "";
      const answer = typeof r.answer === "string" ? r.answer : "";
      if (question && answer) out.push({ question, answer });
    }
  }
  return out;
}

/** biz 페이로드가 BizInfo 형태인지 최소 검증(클라이언트가 1단계 응답을 그대로 회신). */
function isBizInfo(v: unknown): v is BizInfo {
  if (!v || typeof v !== "object") return false;
  const b = v as Record<string, unknown>;
  return (
    typeof b.service_name === "string" &&
    typeof b.solution === "string" &&
    typeof b.language === "string" &&
    Array.isArray(b.missing)
  );
}
