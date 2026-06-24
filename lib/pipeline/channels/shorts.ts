// lib/pipeline/channels/shorts.ts — 쇼츠 생성 (스펙 §7, Haiku).
// 장면별 대본([훅]→[문제]→[해결]→[CTA]) + 자막 + 비주얼 큐, 30~60초.

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, ShortsContent } from "@/lib/multipublish/types";
import { BANNED_CLICHES, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { sanitizeLine } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

const DURATION_MIN = 30;
const DURATION_MAX = 60;

function system(ctx: ChannelContext): string {
  return `너는 숏폼(쇼츠/릴스) 대본 작가다. 아래 코어로 30~60초 영상 대본을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

[포맷]
- scenes: 장면 배열. 흐름은 [훅] → [문제] → [해결] → [CTA] 순서로. 각 { "label": 장면 구분(훅/문제/해결/CTA 등), "script": 나레이션 대사, "subtitle": 화면 자막(짧게), "visual": 비주얼 큐(화면에 뭐가 보이나) }.
- duration_sec: 전체 길이(초), ${DURATION_MIN}~${DURATION_MAX}.

[규칙]
${BANNED_CLICHES}
${SAFETY_RULES}
- 첫 3초 훅이 생명. 자막은 짧고 굵게.
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}.

스키마: { "scenes":[{"label":"","script":"","subtitle":"","visual":""}], "duration_sec":45 }`;
}

export async function generateShorts(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"shorts">> {
  const res = await generate({
    task: "channel.shorts",
    system: system(ctx),
    input: JSON.stringify({ keyword: ctx.keyword, core }),
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<ShortsContent>>(res.text);
  return { content: normalize(parsed, core, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<ShortsContent>, core: Core, ctx: ChannelContext): ShortsContent {
  const k = ctx.keyword || "주제";
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

  return { scenes: scenes.length ? scenes : defaultScenes(core, k), duration_sec };
}

function defaultScenes(core: Core, k: string): ShortsContent["scenes"] {
  return [
    { label: "훅", script: `${k}, 이거 모르면 시간만 날려요`, subtitle: `${k} 핵심만!`, visual: "큰 자막 + 빠른 컷" },
    { label: "문제", script: core.angles[1] ?? "다들 여기서 실수해요", subtitle: "흔한 실수", visual: "X 표시 강조" },
    { label: "해결", script: core.core_message, subtitle: "이렇게 하세요", visual: "체크 표시 + 단계 자막" },
    { label: "CTA", script: "도움 됐다면 저장하고 팔로우!", subtitle: "팔로우 ❤️", visual: "프로필 화살표" },
  ];
}

function mock(core: Core, ctx: ChannelContext): string {
  return JSON.stringify({
    scenes: defaultScenes(core, ctx.keyword || "주제"),
    duration_sec: 45,
  });
}
