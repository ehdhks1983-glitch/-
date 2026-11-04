// lib/wp/quality.ts  [신규 — 워드프레스 자동 발행 v2]
// 발행 전 품질 체크리스트 + 중복 주제 판정. 순수 함수라 브라우저·서버 어디서나 쓴다.
// 배경(조사 반영): 검색엔진은 2024년부터 "대량 생산형 저품질 콘텐츠(scaled content abuse)"를
// 생산 방식(AI/사람)과 무관하게 스팸으로 보고, 2026년 업데이트들에서 단속을 강화했다.
// → 자동 발행일수록 '독자에게 실제로 도움이 되는가'를 기계적으로라도 한 번 거르게 한다.

import { wpHtmlToText } from "./sanitizeHtml";

export interface QualityCheck {
  key: string;
  label: string;
  ok: boolean;
  hint: string;
}

export interface QualityInput {
  title: string;
  html: string;
  excerpt: string;
  tags: string[];
  slug: string;
  metaDescription: string;
  /** 사용자가 입력한 주제/키워드 */
  keyword: string;
  hasFeaturedImage: boolean;
}

export interface QualityReport {
  checks: QualityCheck[];
  passed: number;
  total: number;
}

const LIMITS = {
  minBodyChars: 600,
  minHeadings: 2,
  metaMin: 50,
  metaMax: 155,
  tagsMin: 3,
  tagsMax: 8,
};

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function squash(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "");
}

/** 키워드가 통째로 들어있거나, 2글자 이상 토큰이 모두 들어있으면 포함으로 본다 */
export function containsKeyword(text: string, keyword: string): boolean {
  const t = squash(text);
  const k = squash(keyword);
  if (!k) return true;
  if (t.includes(k)) return true;
  const tokens = keyword
    .toLowerCase()
    .split(/\s+/)
    .map((x) => x.trim())
    .filter((x) => x.length >= 2);
  return tokens.length > 0 && tokens.every((tok) => t.includes(squash(tok)));
}

/** 발행 전 체크리스트 */
export function assessPost(q: QualityInput): QualityReport {
  const text = wpHtmlToText(q.html);
  const headings = (q.html.match(/<h[234]>/g) ?? []).length;
  const firstPara = (q.html.match(/<p>([\s\S]*?)<\/p>/) ?? [])[1] ?? "";
  const meta = (q.metaDescription || q.excerpt).trim();
  const tags = q.tags.filter(Boolean);

  const checks: QualityCheck[] = [
    {
      key: "title-keyword",
      label: "제목에 핵심 키워드",
      ok: containsKeyword(q.title, q.keyword),
      hint: "검색 의도와 바로 연결되도록 제목에 키워드를 넣어요.",
    },
    {
      key: "intro-keyword",
      label: "첫 문단에 키워드",
      ok: containsKeyword(wpHtmlToText(firstPara), q.keyword),
      hint: "도입부에서 무엇에 관한 글인지 분명히 해요.",
    },
    {
      key: "headings",
      label: `소제목 ${LIMITS.minHeadings}개 이상`,
      ok: headings >= LIMITS.minHeadings,
      hint: `지금 ${headings}개. h2/h3로 구조를 나누면 읽기와 검색 모두 좋아져요.`,
    },
    {
      key: "length",
      label: `본문 ${LIMITS.minBodyChars.toLocaleString()}자 이상`,
      ok: text.length >= LIMITS.minBodyChars,
      hint: `지금 ${text.length.toLocaleString()}자. 얇은 글은 '대량 저품질'로 묶일 수 있어요.`,
    },
    {
      key: "list",
      label: "목록·단계 구성",
      ok: /<(ul|ol)>/.test(q.html),
      hint: "절차·항목은 리스트로 정리하면 가독성이 올라가요.",
    },
    {
      key: "faq",
      label: "FAQ(자주 묻는 질문) 섹션",
      ok: /자주 묻는 질문|FAQ|자주 하는 질문/i.test(q.html),
      hint: "실제 궁금증에 답하는 FAQ는 AI 검색 요약에도 잘 잡혀요.",
    },
    {
      key: "meta",
      label: `메타 설명 ${LIMITS.metaMin}~${LIMITS.metaMax}자`,
      ok: meta.length >= LIMITS.metaMin && meta.length <= LIMITS.metaMax,
      hint: `지금 ${meta.length}자. 검색 결과에 보이는 요약이에요.`,
    },
    {
      key: "slug",
      label: "영문 슬러그(URL)",
      ok: SLUG_RE.test(q.slug),
      hint: "한글 URL은 공유 시 깨져 보여요. 영문 소문자-하이픈 형태 권장.",
    },
    {
      key: "image",
      label: "대표 이미지",
      ok: q.hasFeaturedImage,
      hint: "목록·SNS 공유 썸네일로 쓰여요. 없어도 발행은 돼요.",
    },
    {
      key: "internal-link",
      label: "내부 링크 1개 이상",
      ok: /<a href=/.test(q.html),
      hint: "내 사이트의 관련 글로 연결하면 체류·순환이 좋아져요.",
    },
    {
      key: "tags",
      label: `태그 ${LIMITS.tagsMin}~${LIMITS.tagsMax}개`,
      ok: tags.length >= LIMITS.tagsMin && tags.length <= LIMITS.tagsMax,
      hint: `지금 ${tags.length}개.`,
    },
  ];

  return { checks, passed: checks.filter((c) => c.ok).length, total: checks.length };
}

// ───────────────────────── 중복 주제 판정 ─────────────────────────

export function normalizeForCompare(s: string): string {
  return s.toLowerCase().replace(/[^0-9a-z가-힣]/g, "");
}

function bigrams(s: string): Map<string, number> {
  const m = new Map<string, number>();
  for (let i = 0; i < s.length - 1; i++) {
    const g = s.slice(i, i + 2);
    m.set(g, (m.get(g) ?? 0) + 1);
  }
  return m;
}

/** 두 제목의 유사도(0~1, 바이그램 Dice 계수) */
export function titleSimilarity(a: string, b: string): number {
  const x = normalizeForCompare(a);
  const y = normalizeForCompare(b);
  if (x.length < 2 || y.length < 2) return x === y ? 1 : 0;
  const bx = bigrams(x);
  const by = bigrams(y);
  let overlap = 0;
  for (const [g, n] of bx) overlap += Math.min(n, by.get(g) ?? 0);
  return (2 * overlap) / (x.length - 1 + (y.length - 1));
}

/**
 * 키워드와 겹치는 기존 글 제목이 있으면 그 제목을 돌려준다(없으면 null).
 * 키워드가 제목에 통째로 들어있거나 유사도가 threshold 이상이면 중복으로 본다.
 */
export function findDuplicateTopic(
  keyword: string,
  existingTitles: string[],
  threshold = 0.6,
): string | null {
  const k = normalizeForCompare(keyword);
  for (const title of existingTitles) {
    const t = normalizeForCompare(title);
    if (k.length >= 4 && t.includes(k)) return title;
    if (titleSimilarity(keyword, title) >= threshold) return title;
  }
  return null;
}
