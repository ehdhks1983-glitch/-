// lib/pipeline/channels/shorts.ts — 쇼츠 생성 (스펙 §7, Haiku).
// 장면별 대본([훅]→[문제]→[해결]→[CTA]) + 자막 + 비주얼 큐, 30~60초. 자연스러움·구체성(§NATURALNESS).

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, ShortsContent } from "@/lib/multipublish/types";
import { BANNED_CLICHES, MOCK_NOTICE, NATURALNESS, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { sanitizeLine } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

const DURATION_MIN = 30;
const DURATION_MAX = 60;

function system(ctx: ChannelContext): string {
  return `너는 숏폼(쇼츠/릴스) 대본 작가다. 아래 코어로 30~60초 영상 대본을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

${NATURALNESS}

[포맷]
- scenes: 장면 배열. 흐름은 [훅] → [문제] → [해결] → [CTA]. 각 { "label": 장면 구분, "script": 나레이션 대사(구체적으로), "subtitle": 화면 자막(짧게), "visual": 비주얼 큐 }.
- duration_sec: 전체 길이(초), ${DURATION_MIN}~${DURATION_MAX}.

[규칙]
${BANNED_CLICHES}
${SAFETY_RULES}
- 첫 3초 훅이 생명. 대사마다 키워드를 박지 말고 자연스럽게. 자막은 짧고 굵게.
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}.

스키마: { "scenes":[{"label":"","script":"","subtitle":"","visual":""}], "duration_sec":45 }`;
}

export async function generateShorts(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"shorts">> {
  const res = await generate({
    task: "channel.shorts",
    system: system(ctx),
    input: `주제: ${ctx.keyword}\n\ncore:\n${JSON.stringify(core)}`,
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<ShortsContent>>(res.text);
  return { content: normalize(parsed, core), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<ShortsContent>, core: Core): ShortsContent {
  const scenes = (Array.isArray(parsed.scenes) ? parsed.scenes : [])
    .map((s) => ({
      label: sanitizeLine(s?.label, 40),
      script: sanitizeLine(s?.script, 400),
      subtitle: sanitizeLine(s?.subtitle, 120),
      visual: sanitizeLine(s?.visual, 200),
    }))
    .filter((s) => s.script || s.subtitle)
    .slice(0, 8);

  const dur = Number(parsed.duration_sec);
  const duration_sec = Number.isFinite(dur) ? Math.min(DURATION_MAX, Math.max(DURATION_MIN, Math.round(dur))) : 45;

  return { scenes: scenes.length ? scenes : defaultScenes(core), duration_sec };
}

function defaultScenes(core: Core): ShortsContent["scenes"] {
  return [
    { label: "훅", script: "이거 모르고 시작하면 시간만 날려요.", subtitle: "시작 전 꼭 보기", visual: "큰 자막 + 빠른 컷" },
    { label: "문제", script: core.angles[1] ?? "다들 여기서 한 번씩 실수하거든요.", subtitle: "흔한 실수", visual: "X 표시 강조" },
    { label: "해결", script: core.core_message, subtitle: "이렇게 하세요", visual: "체크 표시 + 단계 자막" },
    { label: "CTA", script: "도움 됐으면 저장하고 팔로우!", subtitle: "팔로우 ❤️", visual: "프로필 화살표" },
  ];
}

/** 키리스 목: 첫 장면 대사 상단에 체험 고지 + 키워드 도배 없이 자연스럽게. */
function mock(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "이 주제";
  const scenes = defaultScenes(core);
  scenes[0] = { ...scenes[0], script: `[${MOCK_NOTICE}] ${k}, 이거 모르고 시작하면 시간만 날려요.` };
  return JSON.stringify({ scenes, duration_sec: 45 });
}
