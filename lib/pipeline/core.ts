// lib/pipeline/core.ts — 코어 추출 (스펙 §7 3단계, Haiku). 모든 채널 생성의 단일 입력 'core' 생성.
// 콘텐츠 룰(코드 내장): facts는 출처 있는 항목만(할루시네이션 방지) — §13/§16.
// 품질: 키워드 도배·일반론 금지, 그 주제만의 구체적 내용(§NATURALNESS).

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, Fact, GenOptions } from "@/lib/multipublish/types";
import { NATURALNESS, SAFETY_RULES, monetizeHint, sourcesBlock, toneLabel } from "./prompts";
import { dedupeTags, sanitizeLine, sanitizeTag } from "./sanitize";

export interface CoreContext {
  keyword: string;
  options: GenOptions;
  /** 스크랩 본문(있을 때만 facts 근거가 된다). */
  sources: { url: string; text: string }[];
}

export interface CoreResult {
  core: Core;
  costUsd: number;
  mocked: boolean;
}

const SYSTEM = `너는 해당 분야를 실제로 잘 아는 한국어 콘텐츠 기획자다. 주제(키워드)와 (있다면) 참고자료를 바탕으로 글의 '핵심(코어)'을 뽑아 JSON 객체 하나로만 출력한다. 설명·마크다운·코드펜스 없이 순수 JSON.

${NATURALNESS}

[뽑을 것]
- core_message: 이 주제로 글을 쓸 때 독자에게 전할 '구체적인 한 문장'. 그 주제에만 해당하는 실질적 통찰이어야 한다. (나쁜 예: "OO의 핵심은 기본기를 지키며 꾸준히 하는 것" / 좋은 예: 그 분야에서 실제로 갈리는 포인트를 콕 집은 문장)
- angles: 채널별로 골라 쓸 구체적 포인트 4~6개(짧은 구). 일반론 말고 실제로 다룰 거리.
- facts: [{ "claim": 사실, "source": 참고자료 URL 또는 구절 }]. 출처가 분명한 사실만. 근거 없으면 그 항목은 빼라(할루시네이션 방지). 참고자료가 없으면 facts = [].
- target_reader: 누가 이 글을 검색해 읽을지 구체적으로.
- tone: 아래 톤을 반영한 한 줄.
- tag_candidates: 검색·노출에 실제 쓸 만한 관련 태그 후보 12~15개(해시 # 없이). '키워드+추천/초보/방법'식 변형 도배 금지 — 실제 연관어·동의어·세부주제로.

[규칙]
${SAFETY_RULES}
- 사실(facts)과 추정/주장(angles)을 섞지 않는다.

스키마:
{ "core_message":"", "angles":["",""], "facts":[{"claim":"","source":""}], "target_reader":"", "tone":"", "tag_candidates":["",""] }`;

function buildInput(ctx: CoreContext): string {
  const head = JSON.stringify({
    topic: ctx.keyword,
    tone: toneLabel(ctx.options.tone),
    monetize_hint: monetizeHint(ctx.options),
  });
  return `주제: ${ctx.keyword}\n톤: ${toneLabel(ctx.options.tone)}\n옵션: ${head}\n\n참고자료:\n${sourcesBlock(ctx.sources)}`;
}

export async function extractCore(ctx: CoreContext): Promise<CoreResult> {
  const res = await generate({
    task: "core",
    system: SYSTEM,
    input: buildInput(ctx),
    cacheable: true,
    json: true,
    mock: mockCore(ctx),
  });
  const parsed = safeParseJson<Partial<Core>>(res.text);
  return { core: normalizeCore(parsed, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

/** 모델 출력 → 안전한 Core. 콘텐츠 룰을 코드로 강제. */
export function normalizeCore(parsed: Partial<Core>, ctx: CoreContext): Core {
  const k = ctx.keyword || "이 주제";
  const hasSources = ctx.sources.some((s) => (s.text || "").trim().length > 0);

  // facts: 출처 있는 항목만. 참고자료가 없으면 무조건 빈 배열(근거 없음).
  const facts: Fact[] = hasSources && Array.isArray(parsed.facts)
    ? parsed.facts
        .map((f) => ({ claim: sanitizeLine(f?.claim, 400), source: sanitizeLine(f?.source, 500) }))
        .filter((f) => f.claim && f.source)
        .slice(0, 8)
    : [];

  const angles = arr(parsed.angles, 6, 200);
  const tagCandidates = dedupeTags(
    (Array.isArray(parsed.tag_candidates) ? parsed.tag_candidates : []).map(sanitizeTag).filter(Boolean),
  ).slice(0, 15);

  return {
    // 폴백도 키워드 도배·"핵심은" 문구를 피한 중립 문장으로.
    core_message: sanitizeLine(parsed.core_message, 300) || `${k}에 대해, 막상 해보면 사소한 데서 결과가 갈립니다. 무엇을 먼저 챙겨야 하는지부터 정리해 드릴게요.`,
    angles: angles.length ? angles : ["시작 전 꼭 확인할 것", "초보가 자주 하는 실수", "시간·비용 아끼는 현실 팁", "상황별 선택 기준"],
    facts,
    target_reader: sanitizeLine(parsed.target_reader, 200) || `${k}을(를) 찾아보기 시작한 사람`,
    tone: sanitizeLine(parsed.tone, 120) || toneLabel(ctx.options.tone),
    tag_candidates: tagCandidates.length ? tagCandidates : fallbackTags(k),
  };
}

function arr(v: unknown, maxItems: number, maxLen: number): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => sanitizeLine(x, maxLen)).filter(Boolean).slice(0, maxItems);
}

/** 모델이 태그를 못 줬을 때의 폴백 — 키워드 변형 도배 대신 일반 콘텐츠 태그 + 주제. */
function fallbackTags(k: string): string[] {
  return [k, "입문", "후기", "꿀팁", "정리", "추천", "노하우", "주의사항", "비교", "가이드", "초보", "정보"];
}

/**
 * 키리스 목 모드용 코어. 실제 도메인 지식이 없으므로 '자연스러운 자리표시 초안'을 만든다.
 * 키워드를 매 문장에 박지 않고, 주제는 1~2회만 자연스럽게 언급.
 */
function mockCore(ctx: CoreContext): string {
  const k = ctx.keyword || "이 주제";
  return JSON.stringify({
    core_message: `${k}, 막상 해보면 사소한 차이에서 결과가 갈리더라고요. 처음에 방향만 제대로 잡아두면 시간도 돈도 꽤 아낄 수 있습니다.`,
    angles: [
      "시작 전에 꼭 확인할 것",
      "다들 한 번씩 겪는 실수와 그 이유",
      "돈·시간을 아끼는 현실적인 팁",
      "상황에 따라 달라지는 선택 기준",
      "초보가 자주 묻는 질문",
    ],
    facts: ctx.sources.filter((s) => s.text).map((s, i) => ({
      claim: `참고자료 ${i + 1}에서 확인된 내용(체험 모드라 요약은 자리표시)`,
      source: s.url,
    })),
    target_reader: `이제 막 ${k}에 관심이 생겨 정보를 찾아보는 사람`,
    tone: toneLabel(ctx.options.tone),
    tag_candidates: [k, "입문", "후기", "꿀팁", "정리", "추천", "노하우", "주의사항", "비교", "가이드", "초보", "체크리스트"],
  });
}
