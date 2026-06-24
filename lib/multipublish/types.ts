// lib/multipublish/types.ts
// 곰대리 멀티발행 도메인 타입 (스펙 §6/§7/§10). 파이프라인·DB·API·UI가 공유한다.

/** 발행 채널. 블로그 + 4채널. */
export type Channel = "blog" | "threads" | "instagram" | "cafe" | "shorts";

/** 전체 채널 순서 (스펙 §15.7: 스레드→인스타→카페→쇼츠, 블로그 선두). */
export const ALL_CHANNELS: Channel[] = ["blog", "threads", "instagram", "cafe", "shorts"];

export const CHANNEL_LABEL: Record<Channel, string> = {
  blog: "블로그",
  threads: "스레드",
  instagram: "인스타",
  cafe: "카페",
  shorts: "쇼츠",
};

/** 생성 상태 머신 (스펙 §10). */
export type GenerationStatus = "queued" | "processing" | "done" | "partial" | "failed";

/** core.facts 항목 — 출처 없는 항목은 코어에서 제외(할루시네이션 방지, 스펙 §7). */
export interface Fact {
  claim: string;
  source: string;
}

/** 코어 객체 (스펙 §7). 모든 채널 생성의 단일 입력. */
export interface Core {
  core_message: string;
  angles: string[];
  facts: Fact[];
  target_reader: string;
  tone: string;
  tag_candidates: string[];
}

/** 참고자료 1건 + 스크랩 결과 메타. generations.source_refs(jsonb)에 저장(본문 텍스트는 제외 — 바이트/프라이버시). */
export interface SourceRef {
  url: string;
  /** 스크랩 성공 여부. false면 "팩트 근거 없음" 플래그(스펙 §7.2). */
  ok: boolean;
  /** 추출 본문 길이(문자). */
  chars?: number;
  /** 추출 방식. */
  via?: "cheerio" | "playwright" | "none";
  /** 실패 사유 등 짧은 메모. */
  note?: string;
}

/** 스크랩 결과(워커 내부용) — SourceRef + 실제 본문 텍스트. 본문은 코어추출 입력으로만 쓰고 메타만 영속화. */
export interface ScrapeResult extends SourceRef {
  text: string;
}

/** 톤: 슬라이더(0=정중/전문 ↔ 100=캐주얼/친근). */
export interface GenOptions {
  /** 0~100 톤 슬라이더. */
  tone: number;
  /** 수익화(제휴/광고 의도) 톤 반영. */
  monetize: boolean;
  /** 생성할 채널(기본 전체). */
  channels: Channel[];
}

// ───────────────────────── 채널별 content 구조 ─────────────────────────

/** 블로그 (Sonnet, SEO 포맷, 핵심태그 정확히 10개 — 스펙 §13). */
export interface BlogContent {
  title: string;
  meta_description: string;
  /** 본문 마크다운(소제목/리스트 포함). */
  body_markdown: string;
  /** 핵심 태그 — 정확히 10개(스펙 §16 코어룰). */
  tags: string[];
  /** 썸네일 1:1 가이드(스펙 §13). */
  thumbnail_guide: string;
}

/** 스레드: 연결 체인 3~6개(1=훅→본문→CTA), 해시태그 0~2 (스펙 §7). */
export interface ThreadsContent {
  posts: string[];
  hashtags: string[];
}

/** 인스타: 캡션(첫 2줄 훅)+해시태그 10~20+캐러셀+이미지 가이드 (스펙 §7). */
export interface InstagramContent {
  caption: string;
  hashtags: string[];
  carousel: { title: string; body: string }[];
  image_guide: string;
}

/** 카페: 커뮤니티 톤, 광고티 제거, 댓글 유도 1줄 (스펙 §7). */
export interface CafeContent {
  title: string;
  body: string;
  comment_bait: string;
}

/** 쇼츠: 장면별 대본([훅]→[문제]→[해결]→[CTA])+자막+비주얼 큐, 30~60초 (스펙 §7). */
export interface ShortsContent {
  scenes: { label: string; script: string; subtitle: string; visual: string }[];
  duration_sec: number;
}

/** 채널 → content 타입 매핑. */
export type ChannelContent = {
  blog: BlogContent;
  threads: ThreadsContent;
  instagram: InstagramContent;
  cafe: CafeContent;
  shorts: ShortsContent;
};

/** 채널 산출물 1건 (generation_outputs 행에 대응). */
export interface GenerationOutput<C extends Channel = Channel> {
  channel: C;
  variant_no: number;
  status: "done" | "failed";
  content: C extends Channel ? ChannelContent[C] : unknown;
  ai_cost_usd: number;
  error?: string;
}

/** 생성 1건(읽기 모델) — API/UI가 쓰는 형태. */
export interface Generation {
  id: string;
  keyword: string;
  title: string;
  source_refs: SourceRef[];
  options: GenOptions;
  core: Core | null;
  status: GenerationStatus;
  error: string | null;
  starred: boolean;
  outputs: GenerationOutput[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}
