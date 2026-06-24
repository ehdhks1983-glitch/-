// lib/multipublish/format.ts — 채널 산출물 → 복사용 텍스트(스펙 §10 [복사]).
// content는 jsonb(unknown)이므로 방어적으로 접근한다.

import type {
  BlogContent,
  CafeContent,
  Channel,
  InstagramContent,
  ShortsContent,
  ThreadsContent,
} from "./types";

const tags = (arr: unknown): string =>
  Array.isArray(arr) ? arr.map((t) => `#${t}`).join(" ") : "";

export function channelToCopyText(channel: Channel, content: unknown): string {
  if (!content || typeof content !== "object") return "";
  switch (channel) {
    case "blog": {
      const c = content as BlogContent;
      // ==형광펜== → 노란 하이라이트 span / 핵심정리·CTA는 가운데정렬 div (블로그 에디터 붙여넣기용).
      const body = (c.body_markdown ?? "").replace(
        /==(.+?)==/g,
        '<span style="background-color:#fef08a">$1</span>',
      );
      const summary = (c.key_points ?? []).length
        ? `<div style="text-align:center">\n📌 핵심 정리\n${(c.key_points ?? []).map((p) => `· ${p}`).join("\n")}\n</div>`
        : "";
      const cta = c.cta ? `<div style="text-align:center">${c.cta}</div>` : "";
      const parts = [c.title, "", body];
      if (summary) parts.push("", summary);
      if (cta) parts.push("", cta);
      parts.push("", `태그: ${tags(c.tags)}`);
      if (c.meta_description) parts.push("", `[메타설명] ${c.meta_description}`);
      if (c.thumbnail_guide) parts.push(`[썸네일] ${c.thumbnail_guide}`);
      return parts.join("\n").trim();
    }
    case "threads": {
      const c = content as ThreadsContent;
      const posts = (c.posts ?? []).map((p, i) => `${i + 1}/${(c.posts ?? []).length} ${p}`).join("\n\n");
      return [posts, c.hashtags?.length ? tags(c.hashtags) : ""].filter(Boolean).join("\n\n").trim();
    }
    case "instagram": {
      const c = content as InstagramContent;
      const carousel = (c.carousel ?? []).map((s, i) => `슬라이드 ${i + 1}. ${s.title}\n${s.body}`).join("\n\n");
      return [
        c.caption,
        tags(c.hashtags),
        carousel ? `\n[캐러셀]\n${carousel}` : "",
        c.image_guide ? `[이미지 가이드] ${c.image_guide}` : "",
      ]
        .filter(Boolean)
        .join("\n\n")
        .trim();
    }
    case "cafe": {
      const c = content as CafeContent;
      return [c.title, "", c.body, "", c.comment_bait].join("\n").trim();
    }
    case "shorts": {
      const c = content as ShortsContent;
      const scenes = (c.scenes ?? [])
        .map((s) => `[${s.label}] ${s.script}\n  자막: ${s.subtitle}\n  화면: ${s.visual}`)
        .join("\n\n");
      return `🎬 ${c.duration_sec ?? "30~60"}초\n\n${scenes}`.trim();
    }
    default:
      return "";
  }
}
