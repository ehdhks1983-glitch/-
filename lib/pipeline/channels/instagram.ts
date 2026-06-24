// lib/pipeline/channels/instagram.ts — 인스타 생성 (스펙 §7, Haiku).
// 캡션(첫 2줄 훅) + 해시태그 10~20 + 캐러셀 + 이미지 가이드. 자연스러움·구체성 우선(§NATURALNESS).

import { generate, safeParseJson } from "@/lib/gateway";
import type { Core, InstagramContent } from "@/lib/multipublish/types";
import { BANNED_CLICHES, MOCK_NOTICE, NATURALNESS, SAFETY_RULES, monetizeHint, toneLabel } from "../prompts";
import { dedupeTags, sanitizeBody, sanitizeLine, sanitizeTag } from "../sanitize";
import type { ChannelContext, ChannelGenResult } from "./types";

const HASHTAG_MIN = 10;
const HASHTAG_MAX = 20;

/** 해시태그가 모자랄 때 채우는 일반 태그(키워드 변형 도배 회피). */
const GENERIC_TAGS = ["일상", "정보공유", "꿀팁", "추천", "기록", "데일리", "꿀템", "정리", "초보", "후기", "팁", "노하우"];

function system(ctx: ChannelContext): string {
  return `너는 인스타그램 콘텐츠를 잘 만드는 사람이다. 아래 코어로 인스타 게시물을 JSON 하나로만 출력한다. 설명·코드펜스 없이 순수 JSON.

${NATURALNESS}

[포맷]
- caption: 캡션. 첫 2줄은 더보기 전에 보이는 강한 훅(구체적으로). 이후 본문 + 마지막에 가벼운 행동 유도. 줄바꿈 사용.
- hashtags: ${HASHTAG_MIN}~${HASHTAG_MAX}개(해시 # 없이). 대형/중형/소형 키워드 섞기. '키워드+추천/스타그램'식 변형 도배 금지.
- carousel: 슬라이드 3~7장. 각 { "title": 슬라이드 큰 글자(짧게), "body": 보조 설명(구체적으로) }.
- image_guide: 이미지/디자인 가이드 1~2문장(분위기·색·구도). 정사각 1:1 권장.

[규칙]
${BANNED_CLICHES}
${SAFETY_RULES}
- 캡션·슬라이드마다 키워드를 박지 마라. 자연스럽게.
- ${monetizeHint(ctx.options)}
- 톤: ${toneLabel(ctx.options.tone)}.

스키마: { "caption":"", "hashtags":[], "carousel":[{"title":"","body":""}], "image_guide":"" }`;
}

export async function generateInstagram(core: Core, ctx: ChannelContext): Promise<ChannelGenResult<"instagram">> {
  const res = await generate({
    task: "channel.instagram",
    system: system(ctx),
    input: `주제: ${ctx.keyword}\n\ncore:\n${JSON.stringify(core)}`,
    cacheable: !ctx.regenerate,
    json: true,
    temperature: ctx.regenerate ? 0.95 : 0.8,
    mock: mock(core, ctx),
  });
  const parsed = safeParseJson<Partial<InstagramContent>>(res.text);
  return { content: normalize(parsed, core, ctx), costUsd: res.costUsd, mocked: res.mocked };
}

function normalize(parsed: Partial<InstagramContent>, core: Core, ctx: ChannelContext): InstagramContent {
  const k = ctx.keyword || "이 주제";
  const caption = sanitizeBody(parsed.caption, 2200) || `${core.core_message}\n\n저장해두고 천천히 보세요 👇`;

  // 해시태그 10~20 강제: 모델 → 코어 후보 → 일반 태그(키워드 변형 도배 금지)로 채움.
  let tags = dedupeTags((Array.isArray(parsed.hashtags) ? parsed.hashtags : []).map(sanitizeTag).filter(Boolean));
  if (tags.length < HASHTAG_MIN) {
    tags = dedupeTags([...tags, ...core.tag_candidates.map(sanitizeTag), sanitizeTag(k), ...GENERIC_TAGS].filter(Boolean));
  }
  tags = tags.slice(0, HASHTAG_MAX);

  const carousel = (Array.isArray(parsed.carousel) ? parsed.carousel : [])
    .map((s) => ({ title: sanitizeLine(s?.title, 80), body: sanitizeLine(s?.body, 300) }))
    .filter((s) => s.title || s.body)
    .slice(0, 8);

  return {
    caption,
    hashtags: tags,
    carousel: carousel.length ? carousel : defaultCarousel(core),
    image_guide:
      sanitizeLine(parsed.image_guide, 300) ||
      `1:1 정사각형. 밝고 깔끔한 톤, 슬라이드마다 큰 키워드 + 여백 충분히.`,
  };
}

function defaultCarousel(core: Core) {
  return [
    { title: "시작 전 체크", body: core.angles[0] ?? "준비물과 순서 먼저" },
    { title: "흔한 실수", body: core.angles[1] ?? "남들 기준 말고 내 조건부터" },
    { title: "저장 필수", body: "필요할 때 다시 꺼내 보세요" },
  ];
}

/** 키리스 목: 캡션 상단에 체험 고지 + 키워드 도배 없이 자연스럽게. */
function mock(core: Core, ctx: ChannelContext): string {
  const k = ctx.keyword || "이 주제";
  return JSON.stringify({
    caption: `${MOCK_NOTICE}\n\n${k}, 시작 전에 이것만 알아도 시행착오가 확 줄어요 ✨\n저장해두고 하나씩 보세요!\n\n준비물과 순서부터 챙기고, 남들 기준이 아니라 내 조건(예산·일정)으로 정하는 게 포인트예요.\n\n👉 더 궁금한 건 댓글로 물어보세요.`,
    hashtags: [k, "일상", "정보공유", "꿀팁", "추천", "기록", "데일리", "정리", "초보", "후기"],
    carousel: [
      { title: "시작 전 체크", body: "준비물과 순서를 먼저 확인하면 헤매는 시간이 줄어요." },
      { title: "흔한 실수", body: "급하게 결정하다 비용을 더 쓰는 경우가 많아요." },
      { title: "현실 팁", body: "내 조건부터 적어두고 비교하면 선택이 쉬워져요." },
      { title: "저장 필수 ⭐", body: "필요할 때 다시 꺼내 보세요." },
    ],
    image_guide: "1:1 정사각형. 파스텔 배경 + 큰 키워드 텍스트, 슬라이드 일관된 색.",
  });
}
