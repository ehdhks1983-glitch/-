// lib/wp/types.ts  [신규 — 워드프레스 자동 발행]
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

/** 글 등록 입력(서버 → WP) */
export interface WpNewPost {
  title: string;
  /** 정화된 본문 HTML */
  html: string;
  excerpt: string;
  status: WpPostStatus;
  /** status가 future일 때 필수 */
  dateGmt?: string;
  categoryId?: number;
  /** 태그 이름 배열 — 서버가 id로 변환해 등록 */
  tags: string[];
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
  /** 선택: 추가 요청사항 */
  extra?: string;
}

/** AI 글 생성 결과 */
export interface GeneratedPost {
  title: string;
  /** 허용 태그만 남긴 본문 HTML */
  html: string;
  excerpt: string;
  tags: string[];
}
