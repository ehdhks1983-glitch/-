// lib/wp/serverUtil.ts  [신규 — 워드프레스 자동 발행] ※ 서버 전용
// app/api/wp/* 라우트 공통 헬퍼: 접속 헤더 파싱, 에러 → 사용자 친화 응답 변환.
// 규칙: 내부 에러 상세(스택·코드)는 로그로만, 응답엔 한국어 안내만(기존 api 컨벤션).

import { NextResponse } from "next/server";
import { sanitizeText } from "@/lib/sanitize";
import { WpApiError } from "./client";
import { decodeWpConnection, WP_CONNECTION_HEADER } from "./connection";
import { WpGuardError } from "./guard";
import type { WpConnection } from "./types";

/** 요청 헤더에서 접속 정보 추출(무상태 프록시). 없거나 깨졌으면 null. */
export function readConnection(req: Request): WpConnection | null {
  const raw = req.headers.get(WP_CONNECTION_HEADER);
  if (!raw) return null;
  return decodeWpConnection(raw);
}

/** 접속 정보 없음 → 401 */
export function needConnection(): NextResponse {
  return NextResponse.json(
    { error: "워드프레스 연결 정보가 없어요. [연결 설정]에서 먼저 연결해 주세요." },
    { status: 401 },
  );
}

export function badRequest(message: string): NextResponse {
  return NextResponse.json({ error: message }, { status: 400 });
}

export function tooMany(): NextResponse {
  return NextResponse.json(
    { error: "요청이 많아요. 잠시 후 다시 시도해 주세요." },
    { status: 429 },
  );
}

/** WP/가드/타임아웃 에러 → 사용자 친화 JSON 응답. 원본은 콘솔 로그로만. */
export function wpErrorResponse(err: unknown, logTag: string): NextResponse {
  console.error(`[${logTag}] 실패:`, err);

  if (err instanceof WpGuardError) {
    return NextResponse.json({ error: err.message }, { status: 400 });
  }

  if (err instanceof WpApiError) {
    const status = err.status >= 400 && err.status < 600 ? err.status : 502;
    return NextResponse.json({ error: friendlyWpMessage(err) }, { status });
  }

  if (err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError")) {
    return NextResponse.json(
      { error: "사이트 응답이 너무 늦어요. 잠시 후 다시 시도해 주세요." },
      { status: 504 },
    );
  }

  return NextResponse.json(
    { error: "요청 처리 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." },
    { status: 502 },
  );
}

function friendlyWpMessage(err: WpApiError): string {
  if (err.status === 401) {
    return "인증에 실패했어요. 아이디와 응용 프로그램 비밀번호를 다시 확인해 주세요.";
  }
  if (err.status === 403) {
    return "권한이 없어요. 글/카테고리를 관리할 수 있는 계정(관리자·편집자)인지 확인해 주세요.";
  }
  if (err.code === "rest_no_route" || err.status === 404) {
    return "REST API 경로를 찾을 수 없어요. 사이트 주소를 다시 확인해 주세요.";
  }
  // WP가 준 메시지는 한국어 사이트면 한국어로 온다 — 태그 제거 후 그대로 전달
  const m = sanitizeText(err.message, 180);
  return m || "워드프레스가 요청을 거부했어요.";
}

/** 문자열 필드 안전 추출(트림+길이 제한). 없으면 빈 문자열. */
export function strField(body: Record<string, unknown>, key: string, maxLen: number): string {
  const v = body[key];
  return typeof v === "string" ? v.trim().slice(0, maxLen) : "";
}

/** 0 이상의 정수 필드 추출. 아니면 undefined. */
export function intField(body: Record<string, unknown>, key: string): number | undefined {
  const v = body[key];
  if (typeof v === "number" && Number.isInteger(v) && v >= 0) return v;
  return undefined;
}
