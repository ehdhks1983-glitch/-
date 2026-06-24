// lib/pipeline/core.ts — 코어 추출 (스펙 §7 3단계, Haiku). 모든 채널 생성의 단일 입력 'core' 생성.
// 콘텐츠 룰(코드 내장): facts는 출처 있는 항목만(할루시네이션 방지) — §13/§16.

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, Fact, GenOptions } from "@/lib/multipublish/types";
import { SAFETY_RULES, monetizeHint, sourcesBlock, toneLabel } from "./prompts";
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

const SYSTEM = `너는 콘텐츠 코어 분석가다. 키워드와 (있다면) 참고자료를 읽고 글 전체의 '핵심(코어)'을 뽑아 JSON 객체 하나로만 출력한다. 설명·마크다운·코드펜스 없이 순수 JSON.

[뽑을 것]
- core_message: 글 전체를 관통하는 핵심 메시지 1문장.
- angles: 채널별로 골라 쓸 포인트 3~6개(짧은 구).
- facts: [{ "claim": 사실, "source": 참고자료 URL 또는 구절 }]. 출처가 분명한 사실만 넣는다. 참고자료에 근거가 없으면 그 항목은 넣지 않는다(할루시네이션 방지). 참고자료가 없으면 facts = [].
- target_reader: 이 글이 누구를 위한 것인지.
- tone: 아래 톤을 반영한 한 줄.
- tag_candidates: 블로그에서 10개로 확정할 태그 후보 12~15개(해시 # 없이).

[규칙]
${SAFETY_RULES}
- 사실(facts)과 추정/주장(angles)을 섞지 않는다.
- 한국어로 작성.

스키마:
{ "core_message":"", "angles":["",""], "facts":[{"claim":"","source":""}], "target_reader":"", "tone":"", "tag_candidates":["",""] }`;

function buildInput(ctx: CoreContext): string {
  const head = JSON.stringify({
    keyword: ctx.keyword,
    tone: toneLabel(ctx.options.tone),
    monetize_hint: monetizeHint(ctx.options),
  });
  return `${head}\n\n참고자료:\n${sourcesBlock(ctx.sources)}`;
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
  const k = ctx.keyword || "주제";
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
    core_message: sanitizeLine(parsed.core_message, 300) || `${k}의 핵심을 한눈에 정리합니다.`,
    angles: angles.length ? angles : [`${k} 기본기`, `${k} 흔한 실수`, `${k} 체크리스트`],
    facts,
    target_reader: sanitizeLine(parsed.target_reader, 200) || `${k}에 막 관심을 가진 사람`,
    tone: sanitizeLine(parsed.tone, 120) || toneLabel(ctx.options.tone),
    tag_candidates: tagCandidates.length ? tagCandidates : defaultTags(k),
  };
}

function arr(v: unknown, maxItems: number, maxLen: number): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => sanitizeLine(x, maxLen)).filter(Boolean).slice(0, maxItems);
}

function defaultTags(k: string): string[] {
  return [k, `${k}추천`, `${k}초보`, `${k}팁`, `${k}가이드`, `${k}방법`, `${k}후기`, `${k}정리`, `${k}비교`, `${k}입문`, `${k}꿀팁`, `${k}정보`];
}

/** 키리스 목 모드용 코어(키워드 기반, 파이프라인 E2E 가능하게). */
function mockCore(ctx: CoreContext): string {
  const k = ctx.keyword || "주제";
  return JSON.stringify({
    core_message: `${k}의 핵심은 기본기를 지키며 꾸준히 하는 것이다.`,
    angles: [`${k} 입문자 가이드`, `${k}에서 흔한 실수`, `${k} 시작 전 체크리스트`, `${k} 시간 절약 팁`, `${k} 초보 Q&A`],
    facts: ctx.sources.filter((s) => s.text).map((s, i) => ({
      claim: `${k}와 관련해 참고자료 ${i + 1}에서 확인된 핵심 포인트`,
      source: s.url,
    })),
    target_reader: `${k}에 막 관심을 가진 초보자`,
    tone: toneLabel(ctx.options.tone),
    tag_candidates: defaultTags(k),
  });
}
