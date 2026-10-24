// lib/compliance/industries.ts  [신규 — 컴플라이언스 P0]
// 업종 프리셋. 업종마다 광고 규제가 달라(식품표시광고법·의료법·학원법·화장품법 등)
// 생성 프롬프트 제약, 금칙어 검사, 게시 전 필수 표시 항목을 업종 단위로 묶는다.
// 클라이언트/서버 공용(순수 데이터·함수) — 서버 전용 모듈을 import 하지 않는다.

import type { BizInfo } from "@/lib/ai/types";

export type IndustryId =
  | "general"
  | "food"
  | "beauty"
  | "academy"
  | "medical"
  | "health_food"
  | "cosmetics";

/** 게시 전 공개 페이지에 반드시 표시해야 하는 업종별 항목. */
export type DisclosureField = "academy_reg_no" | "tuition" | "ad_review_no";

export type Disclosures = Partial<Record<DisclosureField, string>>;

export interface IndustryPreset {
  id: IndustryId;
  name: string;
  /** 생성 프롬프트에 그대로 들어가는 업종 규칙(한국어). */
  promptRules: string[];
  required: DisclosureField[];
}

export const INDUSTRIES: IndustryPreset[] = [
  {
    id: "general",
    name: "일반",
    promptRules: [],
    required: [],
  },
  {
    id: "food",
    name: "식당·카페",
    promptRules: [
      "음식·음료가 질병 예방·치료, 면역력·혈당·혈압 개선, 노화 방지에 효과가 있다고 쓰지 않는다(식품표시광고법).",
      "일반 음식을 건강기능식품처럼 보이게 하는 체중 감량·체지방 감소 효능을 쓰지 않는다.",
    ],
    required: [],
  },
  {
    id: "beauty",
    name: "미용실·뷰티샵",
    promptRules: [
      "탈모 치료·두피 치료·모발 재생처럼 의료 효과로 오인될 표현을 쓰지 않는다.",
      "필러·보톡스·레이저 시술 등 의료행위를 제공하는 것처럼 쓰지 않는다.",
    ],
    required: [],
  },
  {
    id: "academy",
    name: "학원·교육",
    promptRules: [
      "합격 보장, 성적 향상 보장, 합격률 수치처럼 근거 없는 결과 약속을 쓰지 않는다.",
      "교습비·등록번호는 운영자가 따로 입력해 페이지 하단에 표시하므로 카피에 지어 넣지 않는다.",
    ],
    required: ["academy_reg_no", "tuition"],
  },
  {
    id: "medical",
    name: "병원·의원",
    promptRules: [
      "환자 치료경험담, 시술 전후 비교, 부작용·통증이 없다는 표현, 완치·재발 없음을 쓰지 않는다(의료법 제56조).",
      "최고·유일·최초·1위 같은 비교·과장 표현과 무료·할인 시술 유인 문구를 쓰지 않는다.",
    ],
    required: [],
  },
  {
    id: "health_food",
    name: "건강기능식품",
    promptRules: [
      "질병 예방·치료 효능, 의약품처럼 보이는 표현, 소비자 체험기를 쓰지 않는다.",
      "기능성은 식약처가 인정한 표현 범위로만 쓰고, 효과를 단정하지 않는다.",
    ],
    required: ["ad_review_no"],
  },
  {
    id: "cosmetics",
    name: "화장품",
    promptRules: [
      "아토피·여드름·탈모 치료, 피부·세포 재생, 염증 완화처럼 의약품으로 오인될 표현을 쓰지 않는다(화장품법).",
      "주름 개선·미백·자외선 차단은 기능성화장품 심사를 받은 제품일 때만 쓸 수 있으니 단정하지 않는다.",
    ],
    required: [],
  },
];

export const INDUSTRY_IDS = INDUSTRIES.map((i) => i.id);

export const DISCLOSURE_META: Record<DisclosureField, { label: string; placeholder: string; maxLen: number }> = {
  academy_reg_no: { label: "학원 등록번호", placeholder: "예) 제1234호", maxLen: 60 },
  tuition: { label: "교습비", placeholder: "예) 월 30만 원(주 3회, 교재비 별도)", maxLen: 120 },
  ad_review_no: { label: "건강기능식품 광고 자율심의 번호", placeholder: "예) 2026-0123456", maxLen: 60 },
};

export function isIndustryId(v: unknown): v is IndustryId {
  return typeof v === "string" && (INDUSTRY_IDS as string[]).includes(v);
}

export function getIndustry(id: IndustryId): IndustryPreset {
  return INDUSTRIES.find((i) => i.id === id) ?? INDUSTRIES[0];
}

// 감지 순서가 중요하다: 더 엄격한 업종(건기식·의료)을 일반 업종(식품·미용)보다 먼저 본다.
// 예) "피부과"는 의료, "피부관리실"은 미용 / "홍삼 건강기능식품"은 식품이 아니라 건기식.
const INDUSTRY_KEYWORDS: { id: IndustryId; keywords: string[] }[] = [
  { id: "health_food", keywords: ["건강기능식품", "건기식", "영양제", "유산균", "프로바이오틱스", "홍삼", "비타민", "오메가3", "콜라겐", "supplement"] },
  { id: "medical", keywords: ["병원", "의원", "피부과", "치과", "한의원", "성형", "클리닉", "정형외과", "안과", "clinic", "hospital", "dental"] },
  { id: "cosmetics", keywords: ["화장품", "스킨케어", "코스메틱", "세럼", "앰플", "선크림", "cosmetic", "skincare"] },
  { id: "academy", keywords: ["학원", "교습소", "과외", "공부방", "입시", "수학", "영어 교육", "academy", "tutoring"] },
  { id: "beauty", keywords: ["미용실", "헤어", "네일", "속눈썹", "왁싱", "뷰티샵", "피부관리", "펌", "salon", "nail"] },
  { id: "food", keywords: ["식당", "카페", "베이커리", "디저트", "음식", "맛집", "반찬", "도시락", "커피", "밀키트", "restaurant", "cafe", "bakery", "food"] },
];

/** 사업정보 키워드로 업종 추정. 매칭 없으면 general. 사용자가 화면에서 바꿀 수 있다. */
export function detectIndustry(
  biz?: Pick<BizInfo, "service_name" | "target_customer" | "main_problem" | "solution"> | null,
): IndustryId {
  if (!biz) return "general";
  const haystack = [biz.service_name, biz.target_customer, biz.main_problem, biz.solution].join(" ").toLowerCase();
  for (const { id, keywords } of INDUSTRY_KEYWORDS) {
    if (keywords.some((k) => haystack.includes(k))) return id;
  }
  return "general";
}

/** 업종의 필수 표시 항목 중 비어 있는 것. */
export function missingDisclosures(industry: IndustryId, disclosures: Disclosures | undefined): DisclosureField[] {
  return getIndustry(industry).required.filter((f) => !(disclosures?.[f] ?? "").trim());
}
