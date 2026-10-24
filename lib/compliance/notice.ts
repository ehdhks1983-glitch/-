// lib/compliance/notice.ts  [신규 — 컴플라이언스 P0]
// AI 기본법(2026-01-22 시행) 제31조 대응 문구.
//  - 사전고지: 생성형 AI 기반 서비스임을 이용 전에 알린다(위반 시 과태료 직접 대상).
//  - 결과물 표시: 서비스 밖으로 나가는 결과물(공개 페이지)에 AI 생성임을 표시한다.
// 문구를 바꾸면 AI_NOTICE_VERSION 을 올린다(승인 기록에 버전이 남는다).

import type { Lang } from "@/lib/ai/types";

export const AI_NOTICE_VERSION = "2026-10-24";

/** lib/ai/config.ts 의 MODEL_CHAINS 프로바이더와 맞춰 유지한다(클라이언트 번들에 config를 넣지 않기 위해 별도 상수). */
const AI_PROVIDERS = "Anthropic(Claude), Google(Gemini), OpenAI(GPT)";

export const AI_PRE_NOTICE =
  `이 서비스는 생성형 AI(${AI_PROVIDERS})로 페이지 문구를 만듭니다. ` +
  "AI가 쓴 문구는 사실과 다르거나 광고 규정에 맞지 않을 수 있으니, 게시 전에 꼭 확인해 주세요. " +
  "입력한 내용은 문구 생성을 위해 위 AI 제공사(국외 포함)로 전송됩니다.";

export const AI_PRE_NOTICE_SHORT = "생성형 AI로 문구를 만듭니다. 게시 전에 내용을 꼭 확인해 주세요.";

export function aiOutputLabel(lang: Lang): string {
  return lang === "en"
    ? "The copy on this page was written with generative AI and reviewed by the operator before publishing."
    : "이 페이지의 문구는 생성형 AI로 작성되었으며, 운영자가 검토한 뒤 게시했습니다.";
}
