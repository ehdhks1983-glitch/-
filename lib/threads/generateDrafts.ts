// lib/threads/generateDrafts.ts  [신규]
// 주제/톤 → Threads 게시글 "초안" N개 생성(AI). 절대 발행하지 않는다 — 사용자가 검토/승인 후 예약한다.
// lib/ai/core 의 폴백 체인(threads 작업)을 재사용. 키가 하나도 없으면 결정적 목 초안.

import { withFallback, safeParseJson, isMockMode } from "@/lib/ai/core";
import { THREADS_MAX_TEXT, THREADS_MAX_DRAFTS } from "./config";

export interface DraftRequest {
  topic: string;
  tone?: string;
  count?: number;
  language?: "ko" | "en";
}

/** 초안 문자열 배열을 반환. 발행/저장은 호출부(라우트)에서 사용자 승인 후 별도로 처리. */
export async function generateThreadDrafts(req: DraftRequest): Promise<string[]> {
  const count = clampCount(req.count);
  const tone = (req.tone || "친근하고 진솔한").trim();
  const lang: "ko" | "en" = req.language === "en" ? "en" : "ko";

  if (isMockMode()) return mockDrafts(req.topic, count, lang);

  const raw = await withFallback("threads", {
    system: buildSystem(tone, count, lang),
    user: buildUser(req.topic, lang),
    json: true,
  });

  const parsed = safeParseJson<{ drafts?: unknown }>(raw);
  const list = Array.isArray(parsed.drafts) ? parsed.drafts : [];
  const cleaned = list
    .map((d) => normalize(d))
    .filter((d) => d.length > 0)
    .slice(0, count);

  // 형식이 어긋나거나 비면 목 초안으로 최소 보장(어차피 사용자 검토 단계라 안전).
  return cleaned.length ? cleaned : mockDrafts(req.topic, count, lang);
}

function buildSystem(tone: string, count: number, lang: "ko" | "en"): string {
  if (lang === "en") {
    return `You write short, natural Threads posts a real person would publish. Output ONLY one JSON object: {"drafts":["...","..."]} with exactly ${count} items — no prose, no markdown, no code fences.
[Rules] Each post under ${THREADS_MAX_TEXT} characters. Conversational and specific, one idea per post. Vary the opening of every post (never start them all the same way). No hashtag spam (0-2 max, only if natural). No emoji spam. Never invent stats, results, or testimonials. No impersonating medical professionals; no guarantees like "100% cure".
[Tone] ${tone}`;
  }
  return `너는 진짜 사람이 올릴 법한 짧고 자연스러운 Threads 글을 쓴다. 출력은 오직 JSON 객체 하나: {"drafts":["...","..."]} — 정확히 ${count}개, 설명·마크다운·코드펜스 없이.
[규칙]
- 각 글은 ${THREADS_MAX_TEXT}자 이내. 한 글에 한 가지 메시지.
- 대화하듯 구체적으로. 도입 문장을 매번 다르게 — 같은 패턴으로 시작 금지(연속 AI 글 티 회피).
- 해시태그 도배 금지(자연스러우면 0~2개). 이모지 남발 금지.
- 입력에 없는 수치·실적·후기는 지어내지 않기.
- 의사/병원/전문의 등 의료 전문가 사칭·연상 금지. "100% 보장" 같은 과장 금지.
- AI 티 나는 상투어("혁신적","게임 체인저","압도적","최적화된") 금지 → 구체 표현으로.
[톤] ${tone}`;
}

function buildUser(topic: string, lang: "ko" | "en"): string {
  const t = topic.trim();
  return lang === "en" ? `Topic / context:\n${t}` : `주제 / 맥락:\n${t}`;
}

function clampCount(n: number | undefined): number {
  const v = Math.floor(Number(n));
  if (!Number.isFinite(v) || v < 1) return 1;
  return Math.min(v, THREADS_MAX_DRAFTS);
}

function normalize(v: unknown): string {
  const s = typeof v === "string" ? v.trim() : "";
  return s.length > THREADS_MAX_TEXT ? s.slice(0, THREADS_MAX_TEXT) : s;
}

/** 키 없이도 흐름을 확인할 수 있는 결정적 목 초안. */
function mockDrafts(topic: string, count: number, lang: "ko" | "en"): string[] {
  const base = (topic || (lang === "en" ? "your work" : "요즘 하는 일")).trim();
  const ko = [
    `${base}, 시작할 땐 별거 아닌 것 같았는데 막상 해보니 챙길 게 많더라고요. 오늘 배운 것 하나만 적어둡니다.`,
    `${base} 관련해서 자주 받는 질문: "이거 진짜 효과 있어요?" 솔직히 케이스 바이 케이스예요. 제 경험은 이랬습니다.`,
    `${base} 하면서 가장 크게 바뀐 습관 하나. 거창한 게 아니라 매일 10분이었어요.`,
    `${base}, 어제는 잘 안 풀렸는데 오늘은 한 걸음 나아갔네요. 기록 남깁니다.`,
    `${base}에 대해 오해하기 쉬운 점 하나 — 빠른 게 아니라 꾸준한 게 이깁니다.`,
  ];
  const en = [
    `${base}: looked simple at first, turned out to have a lot of moving parts. Noting one thing I learned today.`,
    `A question I get a lot about ${base}: "does this actually work?" Honestly, case by case. Here's my experience.`,
    `The biggest habit ${base} changed for me wasn't dramatic — just 10 minutes a day.`,
    `${base} — yesterday was rough, today I moved a step forward. Logging it.`,
    `One easy-to-miss thing about ${base}: consistency beats speed.`,
  ];
  return (lang === "en" ? en : ko).slice(0, count);
}
