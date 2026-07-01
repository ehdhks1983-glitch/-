import type { MetadataRoute } from "next";

const SITE = "https://meomu.kr"; // 운영 도메인 확정 시 교체

// 공개 페이지 사이트맵. 서치콘솔·네이버 서치어드바이저 등록 대비.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE}/apply/host`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE}/apply/creator`, changeFrequency: "monthly", priority: 0.6 },
  ];
}
