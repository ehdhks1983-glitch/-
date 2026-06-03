// lib/seo/meta.ts  [신규]
// 공개 페이지 기본 SEO 메타 생성(GEO 고급 llms.txt/스키마는 2차).

import type { Metadata } from "next";
import type { SectionCopy } from "@/lib/ai/types";

/** 생성된 카피로 기본 메타데이터(title/description/OG) 구성. */
export function buildPageMetadata(fallbackTitle: string, copy: SectionCopy): Metadata {
  const title = copy.hero.headline || fallbackTitle || "PromptSite";
  const description = (copy.hero.subheadline || copy.solution.body || "").slice(0, 160);
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}
