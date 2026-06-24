// lib/scraper/index.ts — 하이브리드 스크래퍼 (스펙 §9).
//   1순위: 네이티브 fetch + cheerio (가벼운 fetch 우선; 네이버 블로그는 모바일 경로)
//   2순위: Playwright fallback (실패/JS 렌더링 시; blog.naver.com은 #mainFrame iframe 진입)
//   값 못 찾으면 3회 재시도 → 스킵 + 로그. Rate limit: 도메인별 최소 간격 + 랜덤 대기.

import { createLogger } from "@/lib/log";
import type { ScrapeResult } from "@/lib/multipublish/types";
import { extractText } from "./extract";
import {
  GENERIC_SELECTORS,
  SCRAPER_CONFIG,
  SITE_RULES,
  USER_AGENTS,
  type SiteRule,
} from "./config";

const log = createLogger("scraper");

/** 도메인별 마지막 요청 시각(rate limit). */
const lastCallByDomain = new Map<string, number>();

/** 여러 URL을 순차 스크랩(rate limit 준수). */
export async function scrapeUrls(urls: string[]): Promise<ScrapeResult[]> {
  const out: ScrapeResult[] = [];
  for (const u of urls) out.push(await scrapeUrl(u));
  return out;
}

/** 단일 URL → 본문 텍스트(ScrapeResult). 실패해도 throw 하지 않고 ok:false 로 보고("팩트 근거 없음" 플래그). */
export async function scrapeUrl(rawUrl: string): Promise<ScrapeResult> {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    log.warn("잘못된 URL", { rawUrl });
    return { url: rawUrl, ok: false, via: "none", note: "잘못된 URL", text: "" };
  }

  const rule = SITE_RULES.find((r) => r.test.test(url.hostname));
  const selectors = dedupe([...(rule?.selectors ?? []), ...GENERIC_SELECTORS]);

  // 정규화된(모바일) fetch URL
  const fetchUrl = new URL(url.toString());
  if (rule?.toMobile) rule.toMobile(fetchUrl);

  let lastErr: string | undefined;
  for (let attempt = 1; attempt <= SCRAPER_CONFIG.maxRetries; attempt++) {
    try {
      await rateLimit(fetchUrl.hostname);
      const html = await httpGet(fetchUrl.toString(), rule?.useMobileUA ?? false);
      const { text, selector } = extractText(html, selectors);

      if (text.length >= SCRAPER_CONFIG.minBodyChars) {
        log.info("추출 성공(cheerio)", { url: rawUrl, chars: text.length, selector });
        return ok(rawUrl, text, "cheerio");
      }

      // 본문 부실 → Playwright fallback (원본 데스크톱 URL + iframe 규칙)
      log.warn("본문 부실 → Playwright 시도", { url: rawUrl, chars: text.length, selector, attempt });
      const pw = await playwrightExtract(url.toString(), rule, selectors);
      if (pw && pw.length >= SCRAPER_CONFIG.minBodyChars) {
        log.info("추출 성공(playwright)", { url: rawUrl, chars: pw.length });
        return ok(rawUrl, pw, "playwright");
      }

      // 마지막 시도에서 cheerio 결과라도 있으면 best-effort 채택
      if (attempt === SCRAPER_CONFIG.maxRetries && text.length > 0) {
        log.warn("best-effort 채택(짧은 본문)", { url: rawUrl, chars: text.length });
        return ok(rawUrl, text, "cheerio");
      }
      lastErr = `본문 ${text.length}자(임계 ${SCRAPER_CONFIG.minBodyChars})`;
    } catch (err) {
      lastErr = err instanceof Error ? err.message : String(err);
      log.warn("시도 실패", { url: rawUrl, attempt, err: lastErr });
      // fetch 실패 시에도 Playwright 시도(JS-only/차단 회피)
      const pw = await playwrightExtract(url.toString(), rule, selectors).catch(() => null);
      if (pw && pw.length >= SCRAPER_CONFIG.minBodyChars) {
        log.info("추출 성공(playwright, fetch 실패 후)", { url: rawUrl, chars: pw.length });
        return ok(rawUrl, pw, "playwright");
      }
    }
    if (attempt < SCRAPER_CONFIG.maxRetries) await sleep(SCRAPER_CONFIG.retryBackoffMs * 2 ** (attempt - 1));
  }

  log.warn("스킵(3회 실패)", { url: rawUrl, lastErr });
  return { url: rawUrl, ok: false, via: "none", note: lastErr ?? "본문 추출 실패", text: "" };
}

function ok(url: string, text: string, via: "cheerio" | "playwright"): ScrapeResult {
  const capped = text.slice(0, SCRAPER_CONFIG.maxBodyChars);
  return { url, ok: true, via, chars: capped.length, text: capped };
}

/** 영속화용 메타만 추출(본문 text 제외). */
export function toSourceRef(r: ScrapeResult) {
  return { url: r.url, ok: r.ok, chars: r.chars, via: r.via, note: r.note };
}

// ───────────────────────── HTTP (네이티브 fetch) ─────────────────────────

async function httpGet(url: string, mobile: boolean): Promise<string> {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), SCRAPER_CONFIG.timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      redirect: "follow",
      headers: {
        "User-Agent": mobile ? USER_AGENTS.mobile : USER_AGENTS.desktop,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally {
    clearTimeout(t);
  }
}

// ───────────────────────── Playwright fallback (lazy) ─────────────────────────
// 브라우저 미설치/미지원 환경에서는 import/launch 가 실패 → null 반환(graceful degrade).

async function playwrightExtract(
  url: string,
  rule: SiteRule | undefined,
  selectors: string[],
): Promise<string | null> {
  if (!SCRAPER_CONFIG.enablePlaywright) return null;

  let browser: import("playwright").Browser | null = null;
  try {
    const { chromium } = await import("playwright");
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      userAgent: rule?.useMobileUA ? USER_AGENTS.mobile : USER_AGENTS.desktop,
      locale: "ko-KR",
    });
    const page = await context.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: SCRAPER_CONFIG.timeoutMs });

    // iframe 규칙이 있으면 해당 프레임 HTML, 없으면 페이지 HTML.
    let html = "";
    if (rule?.iframe) {
      const el = await page.$(rule.iframe);
      const frame = el ? await el.contentFrame() : null;
      html = frame ? await frame.content() : await page.content();
    } else {
      html = await page.content();
    }
    const { text } = extractText(html, selectors);
    return text;
  } catch (err) {
    log.warn("Playwright 사용 불가/실패 — 스킵", { err: err instanceof Error ? err.message : String(err) });
    return null;
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

// ───────────────────────── Rate limit / 유틸 ─────────────────────────

async function rateLimit(domain: string): Promise<void> {
  const now = Date.now();
  const last = lastCallByDomain.get(domain) ?? 0;
  const elapsed = now - last;
  const base = SCRAPER_CONFIG.minIntervalMsPerDomain;
  if (elapsed < base) {
    const jitter = Math.floor(deterministicJitter(domain, now) * SCRAPER_CONFIG.jitterMs);
    await sleep(base - elapsed + jitter);
  }
  lastCallByDomain.set(domain, Date.now());
}

/** 외부 의존 없는 가벼운 0~1 지터(도메인+시각 기반). */
function deterministicJitter(seed: string, salt: number): number {
  let h = salt & 0xffff;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) & 0xffff;
  return (h % 1000) / 1000;
}

function dedupe(arr: string[]): string[] {
  return [...new Set(arr)];
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
