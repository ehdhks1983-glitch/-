// lib/applications.ts
// 신청 폼 필드 스키마 — 폼 UI(클라이언트)와 서버 검증이 같은 정의를 공유한다.
// 서버 전용 import 금지(클라이언트 컴포넌트에서도 불러옴).

export type ApplicationKind = "host" | "creator";

export type FieldType = "text" | "email" | "tel" | "textarea" | "select" | "checkboxes";

export interface FieldDef {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  placeholder?: string;
  options?: string[];
  /** 정화 시 허용 최대 길이 */
  maxLen?: number;
  /** 폼에서 한 줄 전체를 차지할지 */
  full?: boolean;
}

export interface KindConfig {
  kind: ApplicationKind;
  title: string;
  subtitle: string;
  /** 구조화 컬럼으로 승격할 필드 키(검색·정렬용) */
  fields: FieldDef[];
  cta: string;
}

const REGIONS = ["제주", "강원(양양·속초)", "가평·양평", "경기", "서울·인천", "충청", "전라", "경상", "기타"];

export const HOST_CONFIG: KindConfig = {
  kind: "host",
  title: "무료로 캠페인 만들기",
  subtitle: "감성 독채·풀빌라 사장님을 위한 캠페인 신청이에요. 큐레이션 심사 후 연락드려요. (베타 오픈)",
  cta: "무료로 캠페인 신청",
  fields: [
    { name: "stay_name", label: "숙소명", type: "text", required: true, placeholder: "예) 제주 돌담독채", maxLen: 80 },
    { name: "advertiser_name", label: "사장님 성함", type: "text", required: true, placeholder: "성함", maxLen: 40 },
    { name: "stay_region", label: "지역", type: "select", required: true, options: REGIONS },
    {
      name: "stay_type",
      label: "숙소 유형",
      type: "select",
      required: true,
      options: ["독채 펜션", "풀빌라", "한옥스테이", "디자인 스테이", "감성 펜션", "기타"],
    },
    { name: "email", label: "이메일", type: "email", required: true, placeholder: "you@example.com", maxLen: 254 },
    { name: "phone", label: "연락처", type: "tel", placeholder: "010-0000-0000", maxLen: 30 },
    {
      name: "stay_url",
      label: "인스타·홈페이지·예약 링크",
      type: "text",
      placeholder: "https://instagram.com/...",
      maxLen: 300,
      full: true,
    },
    {
      name: "message",
      label: "남기실 말 (선택)",
      type: "textarea",
      placeholder: "공간 소개, 원하는 캠페인 시기 등을 적어주세요.",
      maxLen: 1200,
      full: true,
    },
  ],
};

export const CREATOR_CONFIG: KindConfig = {
  kind: "creator",
  title: "크리에이터 지원",
  subtitle: "여행·숙박·감성 라이프스타일 숏폼 크리에이터를 모십니다. 실제 1박 후 촬영하는 합법 캠페인이에요.",
  cta: "크리에이터로 지원하기",
  fields: [
    { name: "name", label: "이름 / 활동명", type: "text", required: true, placeholder: "성함 또는 활동명", maxLen: 40 },
    {
      name: "platforms",
      label: "주 활동 채널",
      type: "checkboxes",
      required: true,
      options: ["네이버 클립", "인스타 릴스", "유튜브 쇼츠", "틱톡"],
    },
    {
      name: "channelUrl",
      label: "대표 채널 링크",
      type: "text",
      required: true,
      placeholder: "https://instagram.com/...",
      maxLen: 300,
      full: true,
    },
    {
      name: "followers",
      label: "팔로워 규모",
      type: "select",
      required: true,
      options: ["1천 미만", "1천~5천", "5천~1만", "1만~5만", "5만 이상"],
    },
    { name: "region", label: "주 활동 지역", type: "select", required: true, options: REGIONS },
    {
      name: "category",
      label: "콘텐츠 카테고리",
      type: "select",
      required: true,
      options: ["여행", "숙박·스테이", "감성 라이프스타일", "푸드", "기타"],
    },
    { name: "email", label: "이메일", type: "email", required: true, placeholder: "you@example.com", maxLen: 254 },
    {
      name: "message",
      label: "한마디 (선택)",
      type: "textarea",
      placeholder: "대표 콘텐츠 링크나 강점을 적어주세요.",
      maxLen: 1200,
      full: true,
    },
  ],
};

export function configFor(kind: ApplicationKind): KindConfig {
  return kind === "host" ? HOST_CONFIG : CREATOR_CONFIG;
}

export function isApplicationKind(v: unknown): v is ApplicationKind {
  return v === "host" || v === "creator";
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email) && email.length <= 254;
}
