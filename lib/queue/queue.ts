// lib/queue/queue.ts  [신규]
// 발행(=생성) 대기열 — 블로그봇의 `발행대기열.json`(AppData)에 대응하는 웹 등가물.
// v1은 클라이언트 localStorage에 보관한다(서버 마이그레이션 0, 회귀 위험 최소).
// 큐 항목은 "기존 생성 파이프라인에 그대로 투입할 한 줄 프롬프트(idea)"와 상태를 담는다.
//
// 저장소 추상화: 모든 접근은 이 모듈 함수로만 한다. v1.1에서 Supabase 테이블로 바꿀 때
// UI/생성 코드는 그대로 두고 이 파일 내부 구현만 교체하면 된다.
//
// 주의: 브라우저 전용. SSR/사생활모드 등 localStorage 불가 환경은 조용히 빈 큐로 처리한다
//       (기존 page.tsx의 sessionStorage try/catch 무시 컨벤션과 동일).

/** 블로그봇 status("대기"/"발행중"/"완료"/"실패")에 대응. '발행중' → '생성중'. */
export type QueueStatus = "대기" | "생성중" | "완료" | "실패";

/** 큐 항목 1개. 블로그봇 스키마(keyword/opportunity/status/added_at/posted_at)와 1:1 대응. */
export interface QueueItem {
  id: string;
  /** 기존 생성 파이프라인에 투입할 한 줄 프롬프트(블로그봇의 keyword 대응). */
  idea: string;
  /** 이 아이디어가 왜 괜찮은지 한 줄 근거(발굴 시 AI가 채움). */
  rationale: string;
  /** 적합도/전환잠재 점수 0~100 (블로그봇 opportunity 대응, 단 LLM 추정값). */
  fitScore: number;
  /** 발굴에 쓴 시드(출처 추적용). */
  seed: string;
  status: QueueStatus;
  /** 완료 시 생성된 공개 페이지 slug. */
  slug: string;
  /** 완료 시 생성된 프로젝트 id(편집 링크용). */
  projectId: string;
  /** 실패 시 사유(사용자 친화 메시지). */
  error: string;
  /** 큐에 추가된 시각(ISO). 블로그봇 added_at 대응. */
  addedAt: string;
  /** 생성 완료 시각(ISO) 또는 빈 문자열. 블로그봇 posted_at 대응. */
  generatedAt: string;
}

/** 발굴 결과(아이디어 1건). 발굴 모듈/대기열이 공유. */
export interface DiscoveredIdea {
  idea: string;
  rationale: string;
  fitScore: number;
}

const STORAGE_KEY = "promptsite:idea-queue:v1";

/** localStorage 사용 가능 여부(SSR/사생활모드 방어). */
function storage(): Storage | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

function newId(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // 무시 — 아래 폴백
  }
  return `q_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 알 수 없는 형태를 안전한 QueueItem으로 정규화(손상된 저장값 방어). */
function normalize(raw: unknown): QueueItem | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const idea = typeof r.idea === "string" ? r.idea.trim() : "";
  if (!idea) return null;
  const status = (["대기", "생성중", "완료", "실패"] as const).includes(r.status as QueueStatus)
    ? (r.status as QueueStatus)
    : "대기";
  const fit = Number(r.fitScore);
  return {
    id: typeof r.id === "string" && r.id ? r.id : newId(),
    idea,
    rationale: typeof r.rationale === "string" ? r.rationale : "",
    fitScore: Number.isFinite(fit) ? Math.max(0, Math.min(100, Math.round(fit))) : 0,
    seed: typeof r.seed === "string" ? r.seed : "",
    status,
    slug: typeof r.slug === "string" ? r.slug : "",
    projectId: typeof r.projectId === "string" ? r.projectId : "",
    error: typeof r.error === "string" ? r.error : "",
    addedAt: typeof r.addedAt === "string" ? r.addedAt : nowIso(),
    generatedAt: typeof r.generatedAt === "string" ? r.generatedAt : "",
  };
}

/** 큐 전체 로드(블로그봇 "큐 전체 로드"). 항상 배열을 반환(불가 환경/손상 시 빈 배열). */
export function loadQueue(): QueueItem[] {
  const s = storage();
  if (!s) return [];
  try {
    const raw = s.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalize).filter((x): x is QueueItem => x !== null);
  } catch {
    return [];
  }
}

/** 큐 전체 저장(내부 전용). 저장 성공 여부 반환. */
function saveQueue(items: QueueItem[]): boolean {
  const s = storage();
  if (!s) return false;
  try {
    s.setItem(STORAGE_KEY, JSON.stringify(items));
    return true;
  } catch {
    return false;
  }
}

/**
 * 발굴 결과 중 선택분을 status="대기"로 큐에 추가(블로그봇 "큐에 추가").
 * 이미 큐에 있는 동일 idea(공백 정규화 기준)는 건너뛴다(중복 방지).
 * @returns 추가 후 전체 큐
 */
export function addIdeas(ideas: DiscoveredIdea[], seed = ""): QueueItem[] {
  const existing = loadQueue();
  const seen = new Set(existing.map((i) => i.idea.trim().toLowerCase()));
  const additions: QueueItem[] = [];
  for (const d of ideas) {
    const idea = (d?.idea ?? "").trim();
    if (!idea) continue;
    const key = idea.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    const fit = Number(d.fitScore);
    additions.push({
      id: newId(),
      idea,
      rationale: typeof d.rationale === "string" ? d.rationale.trim() : "",
      fitScore: Number.isFinite(fit) ? Math.max(0, Math.min(100, Math.round(fit))) : 0,
      seed,
      status: "대기",
      slug: "",
      projectId: "",
      error: "",
      addedAt: nowIso(),
      generatedAt: "",
    });
  }
  const next = [...existing, ...additions];
  saveQueue(next);
  return next;
}

/** 특정 항목 부분 갱신(블로그봇 "특정 항목 status 갱신"). 없으면 변경 없이 현재 큐 반환. */
export function updateItem(id: string, patch: Partial<Omit<QueueItem, "id">>): QueueItem[] {
  const items = loadQueue();
  let changed = false;
  const next = items.map((it) => {
    if (it.id !== id) return it;
    changed = true;
    return { ...it, ...patch, id: it.id };
  });
  if (changed) saveQueue(next);
  return next;
}

/** 단일 항목 삭제. */
export function removeItem(id: string): QueueItem[] {
  const next = loadQueue().filter((it) => it.id !== id);
  saveQueue(next);
  return next;
}

/** 완료·실패 항목 정리(블로그봇 "완료·실패 정리"). @returns 남은 큐 */
export function clearFinished(): QueueItem[] {
  const next = loadQueue().filter((it) => it.status === "대기" || it.status === "생성중");
  saveQueue(next);
  return next;
}

/** 상태별 개수(대시보드/배지용). */
export function countByStatus(items: QueueItem[] = loadQueue()): Record<QueueStatus, number> {
  const base: Record<QueueStatus, number> = { 대기: 0, 생성중: 0, 완료: 0, 실패: 0 };
  for (const it of items) base[it.status] += 1;
  return base;
}
