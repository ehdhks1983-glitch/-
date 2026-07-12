// app/api/wp/generate/route.ts  [신규 — 워드프레스 자동 발행]
// 주제/키워드 → AI 블로그 글 초안(제목·본문HTML·요약·태그). WP 호출은 없다(생성만).
// 기존 /api/generate 와 동일한 정책: 강한 rate limit + 친화적 에러 메시지.

import { NextResponse } from "next/server";
import { generatePost } from "@/lib/ai/generatePost";
import type { PostGenInput } from "@/lib/wp/types";
import { badRequest, tooMany, strField } from "@/lib/wp/serverUtil";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const maxDuration = 60;

const GENERATE_LIMIT = 12; // 분당 생성 횟수(IP 기준) — 토큰 비용 폭주 방지
const GENERATE_WINDOW_MS = 60_000;

const FIELD_LIMITS = { topic: 100, categoryName: 60, tone: 40, extra: 500 };
const LENGTHS: PostGenInput["length"][] = ["short", "medium", "long"];

export async function POST(req: Request) {
  sweep();
  const rl = rateLimit(clientKey(req, "wp-generate"), GENERATE_LIMIT, GENERATE_WINDOW_MS);
  if (!rl.ok) return tooMany();

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return badRequest("요청 형식이 올바르지 않습니다.");
  }

  const topic = strField(body, "topic", FIELD_LIMITS.topic);
  if (topic.length < 2) {
    return badRequest("어떤 주제(키워드)로 쓸지 2자 이상 입력해 주세요.");
  }

  const lengthRaw = strField(body, "length", 10);
  const length = LENGTHS.find((l) => l === lengthRaw) ?? "medium";

  const input: PostGenInput = {
    topic,
    length,
    categoryName: strField(body, "categoryName", FIELD_LIMITS.categoryName) || undefined,
    tone: strField(body, "tone", FIELD_LIMITS.tone) || undefined,
    extra: strField(body, "extra", FIELD_LIMITS.extra) || undefined,
  };

  try {
    const post = await generatePost(input);
    return NextResponse.json({ post });
  } catch (err) {
    console.error("[api/wp/generate] 실패:", err);
    return NextResponse.json(
      { error: "글 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
