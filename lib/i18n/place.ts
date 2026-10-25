// lib/i18n/place.ts  [신규 — P2 외국인 손님 패키지]
// 매장 정보 정리 · 지도 링크(네이버·구글) · 구조화 데이터(JSON-LD LocalBusiness).
// 같은 매장 사실(상호·주소·전화·영업시간)을 페이지·지도·검색/AI가 똑같이 읽도록 한 곳에서 만든다.

import { sanitizeText } from "@/lib/sanitize";
import type { PageLang, PlaceInfo } from "./langs";

const LIMITS: Record<keyof PlaceInfo, number> = { name: 60, address: 120, phone: 30, hours: 120 };

/** 클라이언트 입력 → 정리된 매장 정보(빈 칸은 뺀다). */
export function parsePlace(input: unknown): PlaceInfo {
  if (!input || typeof input !== "object") return {};
  const r = input as Record<string, unknown>;
  const out: PlaceInfo = {};
  for (const key of Object.keys(LIMITS) as (keyof PlaceInfo)[]) {
    const v = sanitizeText(r[key], LIMITS[key]);
    if (v) out[key] = v;
  }
  return out;
}

export function hasPlace(place: PlaceInfo | null | undefined): boolean {
  return Boolean(place?.address || place?.phone || place?.hours);
}

/** 상호+주소로 지도 검색 링크. 주소가 없으면 null. */
export function mapLinks(place: PlaceInfo): { naver: string; google: string } | null {
  if (!place.address) return null;
  const query = [place.name, place.address].filter(Boolean).join(" ");
  return {
    naver: `https://map.naver.com/p/search/${encodeURIComponent(query)}`,
    google: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`,
  };
}

/** schema.org LocalBusiness. 영업시간은 자유 입력이라 형식 오류를 피하려고 넣지 않는다. */
export function localBusinessJsonLd(place: PlaceInfo, opts: { url: string; lang: PageLang; description: string }) {
  if (!place.name && !place.address) return null;
  const links = mapLinks(place);
  return {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: place.name,
    url: opts.url,
    description: opts.description || undefined,
    address: place.address ? { "@type": "PostalAddress", streetAddress: place.address, addressCountry: "KR" } : undefined,
    telephone: place.phone,
    hasMap: links?.google,
    inLanguage: opts.lang,
  };
}

/** <script type="application/ld+json"> 에 넣을 문자열. `<` 를 이스케이프해 스크립트 탈출(XSS)을 막는다. */
export function jsonLdString(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
