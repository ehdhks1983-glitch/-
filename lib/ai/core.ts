// lib/ai/core.ts  [기존 — promptsite-ai-core]
// 모든 모델 호출의 단일 통로. 프로바이더별 어댑터 + 폴백/타임아웃/재시도 + JSON 안전 파싱.
// 키가 하나도 없으면(또는 PROMPTSITE_MOCK=1) 결정적 목 응답으로 동작 → 키 없이도 파이프라인 개발/테스트 가능.

import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenAI } from "@google/genai";
import OpenAI from "openai";

import {
  API_KEYS,
  GEN_CONFIG,
  MODEL_CHAINS,
  type ModelSpec,
  type TaskKind,
} from "./config";

export interface CallOptions {
  system: string;
  user: string;
  /** JSON 응답을 기대하면 true → 지원 프로바이더에 JSON 모드 힌트 전달. */
  json?: boolean;
}

/**
 * 작업(task)에 정의된 모델 체인을 상위→하위로 시도한다.
 * 키 없는 프로바이더는 skip, 각 모델은 maxRetriesPerModel만큼 재시도, 타임아웃 초과 시 다음 모델.
 * 모두 실패하면 마지막 에러를 묶어 throw.
 */
export async function withFallback(task: TaskKind, opts: CallOptions): Promise<string> {
  if (isMockMode()) {
    if (process.env.NODE_ENV !== "production") {
      console.warn(`[ai] MOCK 모드 (프로바이더 키 없음 / PROMPTSITE_MOCK=1) — task=${task}`);
    }
    return mockResponse(opts);
  }

  const chain = MODEL_CHAINS[task];
  const errors: string[] = [];

  for (const spec of chain) {
    if (!API_KEYS[spec.provider]) continue; // 키 없는 프로바이더 skip

    for (let attempt = 0; attempt <= GEN_CONFIG.maxRetriesPerModel; attempt++) {
      try {
        const text = await withTimeout(callProvider(spec, opts), GEN_CONFIG.requestTimeoutMs);
        if (text && text.trim()) return text;
        throw new Error("빈 응답");
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`${spec.provider}/${spec.model}: ${msg}`);
        if (process.env.NODE_ENV !== "production") {
          console.warn(`[ai] 실패 ${spec.provider}/${spec.model} (시도 ${attempt + 1}): ${msg}`);
        }
        if (attempt < GEN_CONFIG.maxRetriesPerModel) {
          await sleep(GEN_CONFIG.retryBackoffMs * 2 ** attempt);
        }
      }
    }
  }

  throw new Error(
    `모든 모델 호출 실패 (task=${task}): ${errors.join(" | ") || "사용 가능한 프로바이더 키 없음"}`,
  );
}

async function callProvider(spec: ModelSpec, opts: CallOptions): Promise<string> {
  switch (spec.provider) {
    case "anthropic":
      return callAnthropic(spec, opts);
    case "google":
      return callGoogle(spec, opts);
    case "openai":
      return callOpenAI(spec, opts);
  }
}

async function callAnthropic(spec: ModelSpec, opts: CallOptions): Promise<string> {
  const client = new Anthropic({ apiKey: API_KEYS.anthropic, maxRetries: 0 });
  const res = await client.messages.create({
    model: spec.model,
    max_tokens: spec.maxTokens,
    system: opts.system,
    messages: [{ role: "user", content: opts.user }],
  });
  return res.content
    .map((block) => (block.type === "text" ? block.text : ""))
    .join("")
    .trim();
}

async function callGoogle(spec: ModelSpec, opts: CallOptions): Promise<string> {
  const ai = new GoogleGenAI({ apiKey: API_KEYS.google });
  const res = await ai.models.generateContent({
    model: spec.model,
    contents: opts.user,
    config: {
      systemInstruction: opts.system,
      maxOutputTokens: spec.maxTokens,
      ...(opts.json ? { responseMimeType: "application/json" } : {}),
    },
  });
  return (res.text ?? "").trim();
}

async function callOpenAI(spec: ModelSpec, opts: CallOptions): Promise<string> {
  const client = new OpenAI({ apiKey: API_KEYS.openai, maxRetries: 0 });
  const res = await client.chat.completions.create({
    model: spec.model,
    max_completion_tokens: spec.maxTokens,
    messages: [
      { role: "system", content: opts.system },
      { role: "user", content: opts.user },
    ],
    ...(opts.json ? { response_format: { type: "json_object" as const } } : {}),
  });
  return (res.choices[0]?.message?.content ?? "").trim();
}

/** 모델 응답 텍스트에서 JSON 객체만 안전 추출(코드펜스·잡텍스트 방어). */
export function safeParseJson<T>(text: string): T {
  let t = (text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  const a = t.indexOf("{");
  const b = t.lastIndexOf("}");
  if (a !== -1 && b !== -1 && b > a) t = t.slice(a, b + 1);
  return JSON.parse(t) as T;
}

// ───────────────────────── 내부 유틸 ─────────────────────────

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const id = setTimeout(() => reject(new Error(`타임아웃 ${ms}ms 초과`)), ms);
    p.then(
      (v) => {
        clearTimeout(id);
        resolve(v);
      },
      (e) => {
        clearTimeout(id);
        reject(e);
      },
    );
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export function isMockMode(): boolean {
  if (process.env.PROMPTSITE_MOCK === "1") return true;
  return !API_KEYS.anthropic && !API_KEYS.google && !API_KEYS.openai;
}

/** 키 없이도 파이프라인을 돌릴 수 있게 하는 결정적 목 응답. system 스키마로 작업을 구분. */
function mockResponse(opts: CallOptions): string {
  if (opts.system.includes('"html"')) return JSON.stringify(mockPost(opts.user));
  if (opts.system.includes('"hero"')) return JSON.stringify(MOCK_COPY);
  if (opts.system.includes('"options"')) return JSON.stringify(MOCK_CLARIFY);
  return JSON.stringify(MOCK_BIZ);
}

/** 워드프레스 블로그 글 목 응답 — user 페이로드의 주제를 반영해 그럴듯한 초안을 돌려준다. */
function mockPost(user: string): Record<string, unknown> {
  let topic = "블로그 글쓰기";
  try {
    const parsed = JSON.parse(user) as Record<string, unknown>;
    if (typeof parsed["주제_키워드"] === "string" && parsed["주제_키워드"].trim()) {
      topic = parsed["주제_키워드"].trim();
    }
  } catch {
    // user가 JSON이 아니면 기본 주제 사용
  }
  return {
    title: `${topic}, 처음이라면 이 순서대로 시작하세요`,
    html:
      `<p>${topic}에 관심은 있는데 어디서부터 손대야 할지 막막했다면, 이 글 하나로 큰 그림을 잡을 수 있습니다. 복잡한 이론 대신 오늘 바로 해볼 수 있는 것들만 정리했습니다.</p>` +
      `<h2>${topic}, 왜 지금 시작해야 할까</h2>` +
      `<p>미루는 이유는 대부분 정보가 없어서가 아니라 순서가 없어서입니다. 처음 기준을 잡아두면 그다음부터는 반복만 하면 됩니다.</p>` +
      `<h2>시작 전 준비 체크리스트</h2>` +
      `<ul><li>목표를 한 줄로 적어보기 — 무엇이 되면 성공인지</li><li>일주일에 쓸 수 있는 시간 정하기</li><li>참고할 만한 사례 2~3개 모아두기</li></ul>` +
      `<h2>단계별 실행 방법</h2>` +
      `<p>처음에는 작게 시작하는 것이 핵심입니다. 완벽한 준비보다 작은 실행이 결과를 만듭니다.</p>` +
      `<ol><li>가장 작은 단위로 첫 시도를 해봅니다.</li><li>결과를 기록하고 잘된 것 하나, 아쉬운 것 하나를 남깁니다.</li><li>일주일 뒤 같은 작업을 반복하며 개선합니다.</li></ol>` +
      `<h2>자주 하는 실수</h2>` +
      `<p>한 번에 모든 걸 갖추려는 욕심이 가장 큰 걸림돌입니다. <strong>도구보다 꾸준함</strong>이 결과를 좌우합니다.</p>` +
      `<h2>정리</h2>` +
      `<p>${topic}은 시작이 절반입니다. 오늘 체크리스트의 첫 항목 하나만 실행해 보세요. (이 글은 AI 키가 없어 생성된 예시 초안입니다.)</p>`,
    excerpt: `${topic}을 처음 시작하는 사람을 위한 준비 체크리스트와 단계별 실행 방법을 정리했습니다.`,
    tags: [topic, "초보 가이드", "시작하는 법"],
  };
}

const MOCK_BIZ = {
  service_name: "온라인 PT 코칭",
  target_customer: "운동을 시작하려는 30대 직장인",
  main_problem: "퇴근 후 시간이 없고 혼자서는 작심삼일로 끝난다",
  solution: "주 3회 1:1 화상 코칭과 식단 피드백으로 꾸준함을 만든다",
  cta: "무료 상담 신청하기",
  tone: "친근하고 신뢰감 있는",
  language: "ko",
  missing: [
    "구체적 차별점(왜 다른 PT가 아니라 여기인가)",
    "코치 경력·성공 사례 등 신뢰 요소",
    "가격/혜택 노출 여부",
  ],
};

const MOCK_CLARIFY = [
  { question: "가격을 페이지에 표시할까요?", options: ["표시", "상담 시 안내", "비공개"] },
  { question: "코치의 경력이나 자격이 있나요?", options: [] },
  { question: "가장 큰 차별점은 무엇인가요?", options: ["1:1 맞춤", "식단까지 관리", "직장인 시간대 운영"] },
];

const MOCK_COPY = {
  hero: {
    headline: "퇴근 후 30분, 작심삼일을 끝냅니다",
    subheadline: "주 3회 1:1 화상 코칭과 식단 피드백으로 혼자서 못 지키던 운동을 습관으로 만듭니다.",
    cta: "무료 상담 신청하기",
  },
  problem: {
    title: "혼자서는 늘 작심삼일이었죠",
    body: "야근에 치이고, 헬스장은 끊어도 안 가게 되고, 유튜브만 보다 끝나는 밤. 의지가 약해서가 아니라 혼자라서 그렇습니다.",
  },
  solution: {
    title: "옆에서 같이 끌어주는 코치",
    body: "매주 정해진 시간에 화상으로 만나 자세를 잡고, 그날 먹은 걸 사진으로 보내면 피드백이 옵니다. 빠질 수 없는 구조를 만듭니다.",
  },
  features: {
    title: "이렇게 도와드립니다",
    items: [
      { title: "주 3회 1:1 화상 코칭", description: "정해진 시간에 얼굴 보고 운동하니 빠지기 어렵습니다." },
      { title: "식단 사진 피드백", description: "거창한 식단표 대신, 그날 먹은 걸 보내면 바로 코멘트해 드립니다." },
      { title: "직장인 시간대 운영", description: "이른 아침과 늦은 저녁, 퇴근 후에도 시간을 맞출 수 있습니다." },
    ],
  },
  faq: [
    { question: "운동을 한 번도 안 해봤는데 괜찮을까요?", answer: "오히려 그런 분들이 많습니다. 첫 주는 기본 자세부터 천천히 시작합니다." },
    { question: "집에 기구가 없어도 되나요?", answer: "맨몸 운동 위주로 구성하고, 필요하면 저렴한 도구만 안내해 드립니다." },
    { question: "비용이 부담되면요?", answer: "무료 상담에서 목표와 예산을 먼저 듣고 맞는 방식을 함께 정합니다." },
  ],
  cta: { headline: "이번엔 진짜 바꿔봅시다", button: "무료 상담 신청하기" },
};
