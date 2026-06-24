// lib/pipeline/prompts.ts — 프롬프트 공용 블록 (스펙 §13 콘텐츠 룰 내장).
// 팩트 우선/할루시네이션 금지, 광고법(효능 단정 금지), AI 상투어 금지 등을 한 곳에서 관리.

import type { GenOptions } from "@/lib/multipublish/types";

/** 톤 슬라이더(0=정중/전문 ↔ 100=캐주얼/친근) → 한국어 톤 라벨. */
export function toneLabel(tone: number): string {
  const t = Number.isFinite(tone) ? tone : 50;
  if (t <= 20) return "정중하고 전문적인";
  if (t <= 40) return "차분하고 신뢰감 있는";
  if (t <= 60) return "친근하고 균형 잡힌";
  if (t <= 80) return "캐주얼하고 활기찬";
  return "톡톡 튀고 친구처럼 편한";
}

/** 수익화 토글 → 추가 지시(켜져 있으면 자연스러운 전환 유도). */
export function monetizeHint(options: GenOptions): string {
  return options.monetize
    ? "독자가 다음 행동(구매·신청·방문)을 하도록 자연스럽게 유도하되, 과장·허위·압박은 금지."
    : "판매를 강요하지 말고 정보 전달과 공감 위주로.";
}

/** AI 티 나는 상투어 금지 블록(PromptSite 카피 원칙 계승). */
export const BANNED_CLICHES = `[금지 — AI 티 상투어]
"오늘날 빠르게 변화하는","혁신적인","게임 체인저","원스톱","차원이 다른","압도적","최고의","완벽한 솔루션","극대화","최적화된 경험". 전부 구체적 표현으로 대체.`;

/** 안전/광고법 + 할루시네이션 금지 블록(스펙 §13). */
export const SAFETY_RULES = `[안전 · 광고법 · 사실]
- 효능·효과를 단정하지 않는다(특히 건강/의료/금융/다이어트). "100%","완치","보장","즉시 효과" 등 단정 표현 금지.
- 의사·전문가 사칭/연상 금지. 객관 사실과 일반 정보 위주.
- 참고자료(core.facts)에 없는 수치·실적·후기·인용은 절대 지어내지 않는다. 근거 없으면 '상황의 구체성'으로 대신한다.`;

/** 코어 추출 입력용: 스크랩 본문을 자료 블록으로 직렬화(출처 라벨 부여). */
export function sourcesBlock(sources: { url: string; text: string }[], perSourceChars = 4000): string {
  if (!sources.length) {
    return "(참고자료 없음 — facts는 빈 배열로 두고, 일반적으로 알려진 내용만 angles에 담아라. 사실 단정 금지.)";
  }
  return sources
    .map((s, i) => `[자료${i + 1}] 출처: ${s.url}\n${(s.text || "").slice(0, perSourceChars)}`)
    .join("\n\n");
}
