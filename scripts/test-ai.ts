// scripts/test-ai.ts
// Phase 1 검증: analyzePrompt → (clarifyQuestions) → generateCopy 파이프라인을 콘솔로 확인.
// 실행: npm run test:ai   또는   npx tsx scripts/test-ai.ts "프롬프트"
// 키가 없으면 자동으로 목(mock) 모드로 돌아간다(.env.local).

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });

import { analyzePrompt } from "../lib/ai/analyzePrompt";
import { clarifyQuestions, answersToContext } from "../lib/ai/clarifyQuestions";
import { generateCopy } from "../lib/ai/generateCopy";
import { selectTemplate } from "../lib/ai/selectTemplate";

const PROMPT =
  process.argv.slice(2).join(" ") || "온라인 PT 코칭 랜딩, 30대 직장인, 무료 상담 신청";

function hr(label: string) {
  console.log("\n" + "─".repeat(10) + " " + label + " " + "─".repeat(10));
}

async function main() {
  console.log("입력 프롬프트:", PROMPT);

  hr("1) analyzePrompt → BizInfo");
  const biz = await analyzePrompt(PROMPT);
  console.log(JSON.stringify(biz, null, 2));

  hr("추천 템플릿 (selectTemplate)");
  console.log(selectTemplate(biz));

  hr("2) clarifyQuestions (missing 있을 때만)");
  const questions = await clarifyQuestions(biz);
  if (questions.length) {
    console.log(JSON.stringify(questions, null, 2));
  } else {
    console.log("(보완질문 없음 — 바로 카피 생성)");
  }

  // 데모: 보완질문에 첫 보기로 자동 응답(실제 제품에선 사용자가 답한다)
  const answers = questions.map((q) => ({
    question: q.question,
    answer: q.options[0] ?? "(데모 자동응답)",
  }));
  const extra = answersToContext(answers);

  hr("3) generateCopy → SectionCopy");
  const copy = await generateCopy(biz, extra || undefined);
  console.log(JSON.stringify(copy, null, 2));

  hr("완료");
  console.log("✅ 파이프라인 정상 동작");
}

main().catch((err) => {
  console.error("❌ 파이프라인 실패:", err);
  process.exit(1);
});
