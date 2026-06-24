// lib/pipeline/channels/instagram.ts — 인스타 생성 (스펙 §7, Haiku).
// 캡션(첫 2줄 훅) + 해시태그 10~20 + 캐러셀 슬라이드 + 이미지 가이드.

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, InstagramContent } from "@/lib/multipublish/types";
import { BANNED_CLICHES, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { dedupeTags, sanitizeBody, sanitizeLine, sanitizeTag } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

const HASHTAG_MIN = 10;
const HASHTAG_MAX = 20;

function system(ctx: ChannelContext): string {
  return `너는 인스타그램 콘텐츠 기획자다. 아래 코어로 인스타 게시물을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

[포맷]
- caption: 캡션. 첫 2줄은 더보기 전에 보이는 강한 훅. 이후 본문 + 마지막에 행동 유도. 줄바꿈 사용.
- hashtags: ${HASHTAG_MIN}~${HASHTAG_MAX}개(해시 # 없이). 대형/중형/소형 키워드 섞기.
- carousel: 슬라이드 3~7장. 각 { "title": 슬라이드 큰 글자, "body": 보조 설명 }.
- image_guide: 이미지/디자인 가이드 1~2문장(분위기·색·구도). 정사각 1:1 권장.

[규칙]
${BANNED_CLICHES}
${SAFETY_RULES}
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}.

스키마: { "caption":"", "hashtags":[], "carousel":[{"title":"","body":""}], "image_guide":"" }`;
}

export async function generateInstagram(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"instagram">> {
  const res = await generate({
    task: "channel.instagram",
    system: system(ctx),
    input: JSON.stringify({ keyword: ctx.keyword, core }),
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<InstagramContent>>(res.text);
  return { content: normalize(parsed, core, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<InstagramContent>, core: Core, ctx: ChannelContext): InstagramContent {
  const k = ctx.keyword || "주제";
  const caption = sanitizeBody(parsed.caption, 2200) || `${core.core_message}\n\n저장해두고 천천히 보세요 👇`;

  // 해시태그 10~20 강제: 모델 → 후보 → 키워드 변형으로 채움.
  let tags = dedupeTags((Array.isArray(parsed.hashtags) ? parsed.hashtags : []).map(sanitizeTag).filter(Boolean));
  if (tags.length < HASHTAG_MIN) {
    tags = dedupeTags([...tags, ...core.tag_candidates.map(sanitizeTag), ...keywordTags(k)]);
  }
  let i = 1;
  while (tags.length < HASHTAG_MIN) {
    const t = sanitizeTag(`${k}${i++}`);
    if (t && !tags.includes(t)) tags.push(t);
  }
  tags = tags.slice(0, HASHTAG_MAX);

  const carousel = (Array.isArray(parsed.carousel) ? parsed.carousel : [])
    .map((s) => ({ title: sanitizeLine(s?.title, 80), body: sanitizeLine(s?.body, 300) }))
    .filter((s) => s.title || s.body)
    .slice(0, 8);

  return {
    caption,
    hashtags: tags,
    carousel: carousel.length ? carousel : defaultCarousel(core, k),
    image_guide:
      sanitizeLine(parsed.image_guide, 300) ||
      `1:1 정사각형. 밝고 깔끔한 톤, 슬라이드마다 큰 키워드 + 여백 충분히.`,
  };
}

function keywordTags(k: string): string[] {
  return [k, `${k}추천`, `${k}스타그램`, `${k}꿀팁`, `${k}일상`, `${k}정보`, `${k}초보`, `${k}기록`, "데일리", "정보공유"].map(sanitizeTag);
}

function defaultCarousel(core: Core, k: string) {
  return [
    { title: `${k} 핵심`, body: core.core_message },
    { title: core.angles[0] ?? "포인트 1", body: core.angles[1] ?? "" },
    { title: "저장 필수", body: "필요할 때 다시 꺼내 보세요" },
  ];
}

function mock(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "주제";
  return JSON.stringify({
    caption: `${k}, 이것만 알아도 달라져요 ✨\n저장해두고 하나씩 해보세요!\n\n${core.core_message}\n\n👉 더 궁금하면 댓글 주세요.`,
    hashtags: [...core.tag_candidates.slice(0, 8), "데일리", "정보공유", "꿀팁"],
    carousel: [
      { title: `${k} 시작하기`, body: core.core_message },
      { title: core.angles[0] ?? "핵심 1", body: "짧고 굵게 정리" },
      { title: core.angles[1] ?? "핵심 2", body: "흔한 실수 피하기" },
      { title: "저장 필수 ⭐", body: "필요할 때 다시 보기" },
    ],
    image_guide: "1:1 정사각형. 파스텔 배경 + 큰 키워드 텍스트, 슬라이드 일관된 색.",
  });
}
