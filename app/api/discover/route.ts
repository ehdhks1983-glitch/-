// app/api/discover/route.ts  [신규]
// 시드 → 랜딩페이지 아이디어 후보 발굴. 기존 /api/generate 의 검증·rate-limit·에러 처리 패턴을 그대로 따른다.
// AI 에러는 사용자 친화 메시지로만 응답(코드·모델 정보 노출 금지).

import { NextResponse } from "next/server";
import { discoverIdeas, MAX_IDEAS } from "@/lib/ai/discoverIdeas";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_SEED = 300;
const DISCOVER_LIMIT = 8; // 분당 발굴 횟수(IP 기준) — 발굴 1회가 모델 호출이므로 생성보다 빡빡하게
const DISCOVER_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  sweep();
  const rl = rateLimit(clientKey(req, "discover"), DISCOVER_LIMIT, DISCOVER_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json(
      { error: "요청이 많아요. 잠시 후 다시 시도해 주세요." },
      { status: 429 },
    );
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return bad("요청 형식이 올바르지 않습니다.");
  }

  const seedRaw = body.seed;
  if (typeof seedRaw !== "string" || !seedRaw.trim()) {
    return bad("어떤 주제로 아이디어를 찾을지 시드를 적어 주세요.");
  }
  if (seedRaw.length > MAX_SEED) {
    return bad(`시드가 너무 깁니다. ${MAX_SEED}자 이하로 줄여 주세요.`);
  }

  const count = clampCount(body.count);

  try {
    const ideas = await discoverIdeas(seedRaw.trim(), count);
    if (ideas.length === 0) {
      return NextResponse.json(
        { error: "아이디어를 찾지 못했어요. 시드를 조금 더 구체적으로 적어 보세요." },
        { status: 422 },
      );
    }
    return NextResponse.json({ ideas });
  } catch (err) {
    console.error("[api/discover] 실패:", err);
    return NextResponse.json(
      { error: "발굴 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}

function bad(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

function clampCount(v: unknown): number {
  const n = Math.floor(Number(v));
  if (!Number.isFinite(n) || n <= 0) return MAX_IDEAS;
  return Math.min(MAX_IDEAS, n);
}
