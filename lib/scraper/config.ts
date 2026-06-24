// lib/scraper/config.ts — 스크래퍼 설정 외부화 (스펙 §9/§13: 셀렉터·도메인·모바일 경로 하드코딩 금지).
// 사이트 규칙(도메인별 정규화 + 본문 셀렉터 폴백 체인 + Playwright iframe)을 데이터로 관리한다.

function numEnv(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
}

export const SCRAPER_CONFIG = {
  /** 본문 못 찾으면 3회 재시도 → 스킵 (스펙 §9). */
  maxRetries: numEnv("SCRAPER_MAX_RETRIES", 3),
  timeoutMs: numEnv("SCRAPER_TIMEOUT_MS", 15_000),
  /** Rate limit: 같은 도메인 최소 요청 간격(ms) (스펙 §9 네이버 IP/분당 제한). */
  minIntervalMsPerDomain: numEnv("SCRAPER_MIN_INTERVAL_MS", 1_500),
  /** 요청 간 랜덤 추가 대기(ms) 상한. */
  jitterMs: numEnv("SCRAPER_JITTER_MS", 1_200),
  retryBackoffMs: numEnv("SCRAPER_RETRY_BACKOFF_MS", 800),
  /** 이 길이 미만이면 추출 실패로 보고 fallback 시도. */
  minBodyChars: numEnv("SCRAPER_MIN_BODY_CHARS", 200),
  /** 본문 최대 길이(토큰/비용 보호). 초과 시 절단. */
  maxBodyChars: numEnv("SCRAPER_MAX_BODY_CHARS", 20_000),
  /** Playwright fallback 사용 여부(브라우저 없는 환경은 자동 graceful degrade). */
  enablePlaywright: process.env.SCRAPER_DISABLE_PLAYWRIGHT !== "1",
};

export const USER_AGENTS = {
  desktop:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
  mobile:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
};

export interface SiteRule {
  id: string;
  /** host 매칭. */
  test: RegExp;
  /** 모바일/추출 친화 URL로 정규화(in-place 변경). 예: blog.naver.com → m.blog.naver.com */
  toMobile?: (u: URL) => void;
  /** 본문 셀렉터 폴백 체인(여러 개 — 스펙 §9). */
  selectors: string[];
  /** Playwright fallback 시 진입할 iframe 셀렉터(예: 네이버 블로그 #mainFrame). */
  iframe?: string;
  /** 모바일 UA 사용 권장 사이트. */
  useMobileUA?: boolean;
}

/** 사이트별 규칙. 위에서부터 첫 매칭 사용. */
export const SITE_RULES: SiteRule[] = [
  {
    id: "naver-blog",
    test: /(^|\.)blog\.naver\.com$/i,
    // 모바일 경로가 se-main-container를 iframe 없이 바로 렌더(스펙 §9.1).
    toMobile: (u) => {
      u.hostname = "m.blog.naver.com";
    },
    selectors: ["div.se-main-container", "#postViewArea", "div.post_ct", "div.se_component_wrap", "#viewTypeSelector"],
    iframe: "#mainFrame", // 데스크톱 경로 Playwright fallback 시 (스펙 §9.2)
    useMobileUA: true,
  },
  {
    id: "naver-cafe",
    test: /(^|\.)cafe\.naver\.com$/i,
    selectors: ["div.se-main-container", ".article_viewer", "#tbody", "#postContent", ".ContentRenderer"],
    iframe: "#cafe_main",
    useMobileUA: true,
  },
  {
    id: "tistory",
    test: /(^|\.)tistory\.com$/i,
    selectors: [".tt_article_useless_p_margin", ".article_view", ".entry-content", ".contents_style", "article"],
  },
  {
    id: "brunch",
    test: /(^|\.)brunch\.co\.kr$/i,
    selectors: [".wrap_body", ".cont_view", "article"],
  },
];

/** 사이트 규칙이 없을 때 쓰는 일반 본문 셀렉터(뉴스/블로그 공통, 스펙 §9.1 "표준 본문 추출"). */
export const GENERIC_SELECTORS = [
  "article",
  "[itemprop='articleBody']",
  "#articleBody",
  "#article-view-content-div",
  "#newsct_article",
  ".article-body",
  ".article_body",
  ".news_body_area",
  ".post-content",
  ".entry-content",
  "main",
  "[role='main']",
  "#content",
];
