// lib/analytics/source.ts  [신규 — 성과 리포트 P1]
// 방문 유입 경로 분류. utm_source > 인앱 브라우저(UA) > referrer 도메인 순으로 판별해 고정 목록으로 묶는다.
// 개인 식별 정보(IP·UA 원문)는 저장하지 않고 이 분류값만 집계한다. 클라이언트/서버 공용.

export const TRAFFIC_SOURCES = [
  "naver",
  "instagram",
  "kakao",
  "threads",
  "youtube",
  "google",
  "daum",
  "facebook",
  "direct",
  "other",
] as const;

export type TrafficSource = (typeof TRAFFIC_SOURCES)[number];

export const SOURCE_LABELS: Record<TrafficSource, string> = {
  naver: "네이버",
  instagram: "인스타그램",
  kakao: "카카오톡",
  threads: "스레드",
  youtube: "유튜브",
  google: "구글",
  daum: "다음",
  facebook: "페이스북",
  direct: "직접 방문",
  other: "기타",
};

/** 공개 페이지가 판별한 경로를 탭(세션) 동안 보관하는 키 — 방문 집계와 신청 폼이 같은 값을 쓴다. */
export function sourceStorageKey(projectId: string) {
  return `promptsite:source:${projectId}`;
}

export function isTrafficSource(v: unknown): v is TrafficSource {
  return typeof v === "string" && (TRAFFIC_SOURCES as readonly string[]).includes(v);
}

// 도메인/키워드 → 경로. 위에서부터 먼저 맞는 것을 쓴다(threads 는 instagram 보다 먼저).
const SOURCE_MATCHERS: { source: TrafficSource; patterns: RegExp[] }[] = [
  { source: "naver", patterns: [/naver/i] },
  { source: "threads", patterns: [/threads/i] },
  { source: "instagram", patterns: [/instagram/i, /^ig$/i] },
  { source: "kakao", patterns: [/kakao/i] },
  { source: "youtube", patterns: [/youtube/i, /youtu\.be/i] },
  { source: "google", patterns: [/google/i] },
  { source: "daum", patterns: [/daum/i] },
  { source: "facebook", patterns: [/facebook/i, /^fb$/i, /fb\.me/i] },
];

function match(text: string): TrafficSource | null {
  for (const { source, patterns } of SOURCE_MATCHERS) {
    if (patterns.some((p) => p.test(text))) return source;
  }
  return null;
}

/**
 * @param referrer document.referrer
 * @param search   location.search (utm_source 확인용)
 * @param userAgent navigator.userAgent (카카오톡·인스타 인앱 브라우저는 referrer 가 비는 경우가 많음)
 * @param ownHost  이 사이트 호스트 — 내부 이동은 직접 방문으로 본다
 */
export function detectSource(referrer: string, search: string, userAgent = "", ownHost = ""): TrafficSource {
  const utm = new URLSearchParams(search).get("utm_source")?.trim();
  if (utm) return match(utm) ?? "other";

  const inApp = /KAKAOTALK/i.test(userAgent) ? "kakao" : /Instagram/i.test(userAgent) ? "instagram" : /Barcelona/i.test(userAgent) ? "threads" : null;
  if (inApp) return inApp;

  if (!referrer) return "direct";
  let host = "";
  try {
    host = new URL(referrer).hostname;
  } catch {
    return "other";
  }
  if (ownHost && host === ownHost) return "direct";
  return match(host) ?? "other";
}
