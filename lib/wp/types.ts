// lib/wp/types.ts  [업데이트 — 워드프레스 자동 발행 v2 (2026 기준 반영)]
// 워드프레스 연동 전역 도메인 타입. 클라이언트(브라우저)와 서버(API 라우트)가 공유한다.

/** 워드프레스 접속 정보. 서버는 저장하지 않고(무상태) 요청마다 헤더로 받아 중계만 한다. */
export interface WpConnection {
  /** 사이트 주소 (https://example.com 또는 https://example.com/blog) */
  url: string;
  /** 워드프레스 사용자명(아이디) */
  user: string;
  /** 응용 프로그램 비밀번호(Application Password) — 프로필에서 발급 */
  appPassword: string;
}

/** REST 인덱스의 namespaces 로 감지한 SEO 플러그인 */
export type SeoPlugin = "yoast" | "rankmath" | "aioseo" | null;

/** WP REST API 카테고리 (wp/v2/categories) */
export interface WpCategory {
  id: number;
  name: string;
  slug: string;
  description: string;
  /** 상위 카테고리 id (0 = 최상위) */
  parent: number;
  /** 소속 글 개수 */
  count: number;
}

/** 발행 상태. WP 코어 상태 중 이 도구에서 다루는 것만. */
export type WpPostStatus = "publish" | "future" | "draft" | "pending" | "private";

/** 목록/현황 화면용 글 요약 */
export interface WpPostSummary {
  id: number;
  title: string;
  status: WpPostStatus;
  /** GMT 기준 발행(예정) 시각 "YYYY-MM-DDTHH:mm:ss" */
  dateGmt: string;
  link: string;
  categories: number[];
}

/** 글 유형 — 프롬프트 구조 힌트. UI 선택지와 공유한다. */
export type PostType = "info" | "list" | "review" | "compare" | "story";

export const POST_TYPES: Record<PostType, { label: string; guide: string }> = {
  info: {
    label: "정보·가이드형",
    guide: "개념 → 절차(단계별) → 주의점 → 체크리스트 → FAQ 순서. 독자가 읽고 바로 실행할 수 있게.",
  },
  list: {
    label: "리스트형 (N가지)",
    guide: "제목에 숫자를 넣고, 각 항목은 h3 소제목 + 2~3문장 + '왜 좋은지' 한 줄. 마지막에 고르는 기준 정리.",
  },
  review: {
    label: "리뷰·후기형",
    guide: "실제 사용 관점. 장점 → 단점 → 이런 분께 추천 → 대안 순서. 과장 금지, 단정 대신 조건부 표현.",
  },
  compare: {
    label: "비교·선택 가이드형",
    guide: "비교 기준을 먼저 정의 → 항목별 비교(리스트) → 상황별 추천 → 결론 한 문단.",
  },
  story: {
    label: "경험담·칼럼형",
    guide: "1인칭 경험·관찰로 시작 → 배운 점 → 독자에게 적용 팁. 담백하고 구체적으로.",
  },
};

/** 내부 링크 후보(내 사이트의 기존 발행 글) */
export interface InternalLinkCandidate {
  title: string;
  url: string;
}

/** SEO 플러그인(Yoast/RankMath)에 함께 보내는 메타 필드 */
export interface WpSeoFields {
  seoTitle: string;
  metaDescription: string;
  focusKeyword: string;
}

/** 글 등록 입력(서버 → WP) */
export interface WpNewPost {
  title: string;
  /** 정화된 본문 HTML (format=blocks 면 서버가 블록 마크업으로 변환해 전송) */
  html: string;
  excerpt: string;
  status: WpPostStatus;
  /** status가 future일 때 필수 */
  dateGmt?: string;
  categoryId?: number;
  /** 태그 이름 배열 — 서버가 id로 변환해 등록 */
  tags: string[];
  /** 영문 슬러그(URL). 비우면 WP가 제목으로 자동 생성 */
  slug?: string;
  /** 대표 이미지(미디어 id) */
  featuredMediaId?: number;
  /** SEO 메타(플러그인이 있을 때 반영) */
  seo?: WpSeoFields;
  /** blocks = 블록 에디터 마크업(권장), classic = HTML 그대로 */
  format: "blocks" | "classic";
}

/** AI 글 생성 입력 */
export interface PostGenInput {
  /** 주제 또는 핵심 키워드 */
  topic: string;
  /** 선택: 글이 속할 카테고리 이름(글 성격 힌트) */
  categoryName?: string;
  /** 선택: 말투/톤 */
  tone?: string;
  /** 분량 */
  length: "short" | "medium" | "long";
  /** 글 유형 */
  postType?: PostType;
  /** 선택: 추가 요청사항 */
  extra?: string;
  /** 선택: 내부 링크 후보(이 목록의 URL만 본문에 링크 가능) */
  internalLinks?: InternalLinkCandidate[];
  /** 선택: 내 사이트 호스트 — 본문 링크는 이 호스트로만 허용 */
  siteHost?: string;
}

/** AI 글 생성 결과 */
export interface GeneratedPost {
  title: string;
  /** 허용 태그만 남긴 본문 HTML (내부 링크 a href 포함 가능) */
  html: string;
  excerpt: string;
  tags: string[];
  /** 영문 슬러그(URL) — 검증 실패 시 빈 문자열(WP 자동 생성) */
  slug: string;
  seoTitle: string;
  metaDescription: string;
  focusKeyword: string;
}
