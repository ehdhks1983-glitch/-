// lib/brand.ts
// 브랜드 상수 한 곳 모음. 카피·메타·푸터에서 공통 사용.

export const BRAND = {
  /** 워드마크 전체 */
  name: "머무는순간",
  /** 워드마크에서 강조(accent) 처리할 끝부분 */
  nameLead: "머무는",
  nameAccent: "순간",
  /** 한 줄 정의 */
  tagline: "감성 스테이·독채 펜션 전문 숏폼 체험단",
  oneLiner:
    "비주얼 되는 감성 스테이만 골라, 공정위 100% 합법으로, 숏폼(릴스·네이버 클립)으로 알립니다.",
  /** 연락 채널(운영 단계에서 실제 값으로 교체) */
  email: "hello@meomu.kr",
  /** 첫 타깃: 기획안 모듈 11 기본값 — 운영 중 조정 */
  defaultRegionNote: "현재 제주·강원(양양·속초)·가평·양평 권역 우선 운영",
} as const;

/** 패키지 가격표 (기획안 모듈 4 기준안 — 운영 중 조정) */
export const PACKAGES = [
  {
    id: "basic",
    name: "베이직",
    price: "20만~35만원",
    summary: "첫 노출용",
    items: ["크리에이터 3명", "릴스 또는 네이버 클립 각 1개", "실제 1박 숙박 제공", "공정위 표기 100% 적용"],
    featured: false,
  },
  {
    id: "standard",
    name: "스탠다드",
    price: "45만~70만원",
    summary: "가장 추천",
    items: [
      "크리에이터 5명",
      "AI 소재팩(광고·예약용 변형 10개)",
      "실제 1박 숙박 제공",
      "9:16 세로형 + 네이버 클립 동시 업로드",
    ],
    featured: true,
  },
  {
    id: "premium",
    name: "프리미엄",
    price: "90만~150만원",
    summary: "풀빌라·고급 스테이",
    items: [
      "감성 전문 크리에이터 1~2명(매크로)",
      "마이크로 크리에이터 5명",
      "AI 소재팩 + 다국어 변형",
      "조회수·도달·예약 유입 성과 리포트",
    ],
    featured: false,
  },
] as const;
