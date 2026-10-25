// lib/i18n/langs.ts  [신규 — P2 외국인 손님 패키지]
// 공개 페이지 언어. 원문은 한국어(또는 영어)이고, 외국인 손님용 번역본을 영어·일본어·중국어(간체·번체)로 만든다.
// 2026 1~9월 방한객 상위: 중국·일본·대만·홍콩(번체) → 간체와 번체를 따로 둔다(조사 보고서 참고).

import type { SectionCopy } from "@/lib/ai/types";

export const FOREIGN_LANGS = ["en", "ja", "zh-CN", "zh-TW"] as const;
export type ForeignLang = (typeof FOREIGN_LANGS)[number];
export type PageLang = "ko" | ForeignLang;

export const LANG_NAMES: Record<PageLang, string> = {
  ko: "한국어",
  en: "English",
  ja: "日本語",
  "zh-CN": "简体中文",
  "zh-TW": "繁體中文",
};

export function isForeignLang(v: unknown): v is ForeignLang {
  return typeof v === "string" && (FOREIGN_LANGS as readonly string[]).includes(v);
}

/** 언어별 번역본: 페이지 문구 + 구글 비즈니스 프로필용 소개문·해시태그 + 영업시간 번역. */
export interface Translation {
  copy: SectionCopy;
  summary: string;
  hashtags: string[];
  hours: string;
}

export type Translations = Partial<Record<ForeignLang, Translation>>;

/** 매장 정보(공개 페이지 '매장 안내'·지도 링크·구조화 데이터용). 모두 선택 입력. */
export interface PlaceInfo {
  name?: string;
  address?: string;
  phone?: string;
  hours?: string;
}
