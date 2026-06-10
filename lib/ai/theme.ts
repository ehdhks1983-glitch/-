// lib/ai/theme.ts  [신규]
// 업종별 컬러 테마. 사업정보 키워드로 팔레트를 자동 선택해 템플릿에 주입한다.
// 주의: Tailwind는 소스에 적힌 "리터럴 클래스 문자열"만 컴파일하므로
//       클래스는 반드시 이 파일에 통째로 적는다(동적 조합 금지).

import type { BizInfo } from "./types";

export type ThemeId = "indigo" | "emerald" | "amber" | "rose" | "sky" | "violet";

export interface Theme {
  id: ThemeId;
  /** 라이트 배경 배지 칩 */
  badge: string;
  /** 다크 배경 배지 칩 */
  badgeOnDark: string;
  /** 주 CTA 버튼(라이트/다크 공용) */
  btnPrimary: string;
  /** 강조 텍스트(라이트 배경) */
  accentText: string;
  /** 강조 텍스트(다크 배경) */
  accentTextOnDark: string;
  /** 기능 아이콘 칩(라이트) */
  iconChip: string;
  /** 기능 아이콘 칩(다크) */
  iconChipOnDark: string;
  /** 히어로 글로우(라이트) */
  heroGlow: string;
  /** 히어로 글로우(다크) */
  heroGlowDark: string;
  /** 포인트 라인/바 */
  bar: string;
}

export const THEMES: Record<ThemeId, Theme> = {
  indigo: {
    id: "indigo",
    badge: "border-indigo-200 bg-indigo-50 text-indigo-700",
    badgeOnDark: "border-indigo-400/30 bg-indigo-500/10 text-indigo-300",
    btnPrimary: "bg-indigo-600 hover:bg-indigo-500 shadow-indigo-600/25",
    accentText: "text-indigo-600",
    accentTextOnDark: "text-indigo-300",
    iconChip: "bg-indigo-100 text-indigo-600",
    iconChipOnDark: "bg-indigo-500/20 text-indigo-300",
    heroGlow: "bg-[radial-gradient(55%_45%_at_50%_0%,rgba(99,102,241,0.16),transparent)]",
    heroGlowDark: "bg-[radial-gradient(60%_50%_at_50%_0%,rgba(99,102,241,0.28),transparent)]",
    bar: "bg-indigo-500",
  },
  emerald: {
    id: "emerald",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-700",
    badgeOnDark: "border-emerald-400/30 bg-emerald-500/10 text-emerald-300",
    btnPrimary: "bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/25",
    accentText: "text-emerald-600",
    accentTextOnDark: "text-emerald-300",
    iconChip: "bg-emerald-100 text-emerald-600",
    iconChipOnDark: "bg-emerald-500/20 text-emerald-300",
    heroGlow: "bg-[radial-gradient(55%_45%_at_50%_0%,rgba(16,185,129,0.14),transparent)]",
    heroGlowDark: "bg-[radial-gradient(60%_50%_at_50%_0%,rgba(16,185,129,0.25),transparent)]",
    bar: "bg-emerald-500",
  },
  amber: {
    id: "amber",
    badge: "border-amber-200 bg-amber-50 text-amber-800",
    badgeOnDark: "border-amber-400/30 bg-amber-500/10 text-amber-300",
    btnPrimary: "bg-amber-600 hover:bg-amber-500 shadow-amber-600/25",
    accentText: "text-amber-700",
    accentTextOnDark: "text-amber-300",
    iconChip: "bg-amber-100 text-amber-700",
    iconChipOnDark: "bg-amber-500/20 text-amber-300",
    heroGlow: "bg-[radial-gradient(55%_45%_at_50%_0%,rgba(217,119,6,0.13),transparent)]",
    heroGlowDark: "bg-[radial-gradient(60%_50%_at_50%_0%,rgba(217,119,6,0.25),transparent)]",
    bar: "bg-amber-500",
  },
  rose: {
    id: "rose",
    badge: "border-rose-200 bg-rose-50 text-rose-700",
    badgeOnDark: "border-rose-400/30 bg-rose-500/10 text-rose-300",
    btnPrimary: "bg-rose-600 hover:bg-rose-500 shadow-rose-600/25",
    accentText: "text-rose-600",
    accentTextOnDark: "text-rose-300",
    iconChip: "bg-rose-100 text-rose-600",
    iconChipOnDark: "bg-rose-500/20 text-rose-300",
    heroGlow: "bg-[radial-gradient(55%_45%_at_50%_0%,rgba(225,29,72,0.12),transparent)]",
    heroGlowDark: "bg-[radial-gradient(60%_50%_at_50%_0%,rgba(225,29,72,0.22),transparent)]",
    bar: "bg-rose-500",
  },
  sky: {
    id: "sky",
    badge: "border-sky-200 bg-sky-50 text-sky-700",
    badgeOnDark: "border-sky-400/30 bg-sky-500/10 text-sky-300",
    btnPrimary: "bg-sky-600 hover:bg-sky-500 shadow-sky-600/25",
    accentText: "text-sky-600",
    accentTextOnDark: "text-sky-300",
    iconChip: "bg-sky-100 text-sky-600",
    iconChipOnDark: "bg-sky-500/20 text-sky-300",
    heroGlow: "bg-[radial-gradient(55%_45%_at_50%_0%,rgba(2,132,199,0.14),transparent)]",
    heroGlowDark: "bg-[radial-gradient(60%_50%_at_50%_0%,rgba(2,132,199,0.25),transparent)]",
    bar: "bg-sky-500",
  },
  violet: {
    id: "violet",
    badge: "border-violet-200 bg-violet-50 text-violet-700",
    badgeOnDark: "border-violet-400/30 bg-violet-500/10 text-violet-300",
    btnPrimary: "bg-violet-600 hover:bg-violet-500 shadow-violet-600/25",
    accentText: "text-violet-600",
    accentTextOnDark: "text-violet-300",
    iconChip: "bg-violet-100 text-violet-600",
    iconChipOnDark: "bg-violet-500/20 text-violet-300",
    heroGlow: "bg-[radial-gradient(55%_45%_at_50%_0%,rgba(124,58,237,0.14),transparent)]",
    heroGlowDark: "bg-[radial-gradient(60%_50%_at_50%_0%,rgba(124,58,237,0.25),transparent)]",
    bar: "bg-violet-500",
  },
};

const THEME_KEYWORDS: { id: ThemeId; keywords: string[] }[] = [
  {
    id: "emerald",
    keywords: ["운동", "헬스", "피트니스", " pt", "pt ", "피티", "퍼스널", "요가", "다이어트", "건강", "웰니스", "친환경", "fitness", "health", "wellness", "gym", "yoga"],
  },
  {
    id: "amber",
    keywords: ["디저트", "베이커리", "카페", "음식", "식당", "푸드", "요리", "맛집", "커피", "food", "cafe", "bakery", "restaurant", "coffee", "dessert"],
  },
  {
    id: "rose",
    keywords: ["뷰티", "미용", "화장품", "네일", "헤어", "웨딩", "패션", "beauty", "salon", "wedding", "fashion", "cosmetic", "nail"],
  },
  {
    id: "sky",
    keywords: ["교육", "클래스", "강의", "학습", "스터디", "코딩 교육", "과외", "학원", "edu", "class", "course", "learn", "academy", "tutoring"],
  },
  {
    id: "violet",
    keywords: ["마케팅", "대행", "에이전시", "디자인", "크리에이티브", "스튜디오", "브랜딩", "agency", "marketing", "creative", "studio", "branding"],
  },
];

/** 사업정보 키워드로 테마 선택. 매칭 없으면 indigo(기본 SaaS 톤). */
export function selectTheme(biz?: Pick<BizInfo, "service_name" | "target_customer" | "main_problem" | "solution" | "tone"> | null): Theme {
  if (!biz) return THEMES.indigo;
  const haystack = [biz.service_name, biz.target_customer, biz.main_problem, biz.solution, biz.tone]
    .join(" ")
    .toLowerCase();
  for (const { id, keywords } of THEME_KEYWORDS) {
    if (keywords.some((k) => haystack.includes(k))) return THEMES[id];
  }
  return THEMES.indigo;
}
