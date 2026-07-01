import type { MetadataRoute } from "next";

// 검색엔진 크롤링 규칙. 운영자 화면(/admin)·API 는 색인 제외.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin", "/api/", "/login", "/signup"],
    },
    sitemap: "https://meomu.kr/sitemap.xml",
  };
}
