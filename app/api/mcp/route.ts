// app/api/mcp/route.ts  [신규 — P2 MCP 연동]
// AI 비서용 MCP 엔드포인트(Streamable HTTP, stateless). POST 로 JSON-RPC 메시지를 받아 JSON 으로 응답한다.
// 인증: Authorization: Bearer <개인 액세스 토큰>(대시보드 → 연동에서 발급). 토큰 없이도 문구 검사·규칙 조회는 가능.

import { createSupabaseAdmin } from "@/lib/db/supabase-server";
import { resolveToken } from "@/lib/db/apiTokens";
import { handleMessage, rpcError, RPC } from "@/lib/mcp/protocol";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const maxDuration = 60;

const MCP_LIMIT = 120; // 분당 요청(IP 기준)
const MCP_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  sweep();
  if (!rateLimit(clientKey(req, "mcp"), MCP_LIMIT, MCP_WINDOW_MS).ok) {
    return Response.json(rpcError(null, RPC.INTERNAL, "요청이 많아요. 잠시 후 다시 시도해 주세요."), { status: 429 });
  }

  let payload: unknown;
  try {
    payload = await req.json();
  } catch {
    return Response.json(rpcError(null, RPC.PARSE, "Parse error"), { status: 400 });
  }

  const admin = createSupabaseAdmin();
  const bearer = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "").trim();
  const owner = admin && bearer ? await resolveToken(admin, bearer) : null;
  const ctx = { origin: new URL(req.url).origin, owner, admin };

  // 2025-03-26 이전 클라이언트의 배치(배열)도 받아 준다
  const messages = Array.isArray(payload) ? payload : [payload];
  const responses = (await Promise.all(messages.map((m) => handleMessage(m, ctx)))).filter((r) => r !== null);

  if (responses.length === 0) return new Response(null, { status: 202 });
  return Response.json(Array.isArray(payload) ? responses : responses[0]);
}

// 서버→클라이언트 SSE 스트림과 세션은 쓰지 않는다(stateless).
export async function GET() {
  return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
}

export async function DELETE() {
  return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
}
