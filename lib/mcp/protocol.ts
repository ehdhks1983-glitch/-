// lib/mcp/protocol.ts  [신규 — P2 MCP 연동]
// MCP(Model Context Protocol) 최소 서버: JSON-RPC 2.0 위에서 initialize · ping · tools/list · tools/call 만 지원.
// 상태를 두지 않는(stateless) Streamable HTTP 방식 — 요청마다 JSON 응답 하나를 돌려준다.

import { TOOLS, ToolError, type ToolContext } from "./tools";

export const SERVER_INFO = { name: "promptsite", title: "PromptSite (곰대리)", version: "1.0.0" };
const SUPPORTED_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];

const INSTRUCTIONS =
  "소상공인 랜딩페이지 도구입니다. 광고 문구 검사(check_ad_copy)는 토큰 없이 쓸 수 있고, " +
  "내 페이지·성과 조회와 초안 만들기는 액세스 토큰이 필요합니다. 이 서버는 게시(공개)를 하지 않습니다 — " +
  "초안은 사장님이 편집 화면에서 검사 결과를 확인하고 승인해야 공개됩니다.";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: Record<string, unknown>;
}

type JsonRpcResponse =
  | { jsonrpc: "2.0"; id: string | number | null; result: unknown }
  | { jsonrpc: "2.0"; id: string | number | null; error: { code: number; message: string } };

export const RPC = { PARSE: -32700, INVALID_REQUEST: -32600, METHOD_NOT_FOUND: -32601, INVALID_PARAMS: -32602, INTERNAL: -32603 };

export function rpcError(id: string | number | null, code: number, message: string): JsonRpcResponse {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function isRequest(v: unknown): v is JsonRpcRequest {
  return !!v && typeof v === "object" && (v as JsonRpcRequest).jsonrpc === "2.0" && typeof (v as JsonRpcRequest).method === "string";
}

/** 메시지 하나 처리. 알림(id 없음)이면 null(응답 없음). */
export async function handleMessage(msg: unknown, ctx: ToolContext): Promise<JsonRpcResponse | null> {
  if (!isRequest(msg)) {
    // 클라이언트가 보낸 응답 메시지(result/error)는 처리할 게 없다
    if (msg && typeof msg === "object" && "jsonrpc" in msg && !("method" in msg)) return null;
    return rpcError(null, RPC.INVALID_REQUEST, "Invalid Request");
  }
  const isNotification = msg.id === undefined;
  const id = msg.id ?? null;

  switch (msg.method) {
    case "initialize": {
      const requested = String(msg.params?.protocolVersion ?? "");
      return {
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: SUPPORTED_VERSIONS.includes(requested) ? requested : SUPPORTED_VERSIONS[0],
          capabilities: { tools: { listChanged: false } },
          serverInfo: SERVER_INFO,
          instructions: INSTRUCTIONS,
        },
      };
    }
    case "ping":
      return isNotification ? null : { jsonrpc: "2.0", id, result: {} };
    case "tools/list":
      return {
        jsonrpc: "2.0",
        id,
        result: {
          tools: TOOLS.map(({ name, title, description, inputSchema, annotations }) => ({ name, title, description, inputSchema, annotations })),
        },
      };
    case "tools/call": {
      const name = msg.params?.name;
      const tool = TOOLS.find((t) => t.name === name);
      if (!tool) return rpcError(id, RPC.INVALID_PARAMS, `Unknown tool: ${String(name)}`);
      const args = (msg.params?.arguments && typeof msg.params.arguments === "object" ? msg.params.arguments : {}) as Record<string, unknown>;
      try {
        const data = await tool.run(args, ctx);
        return {
          jsonrpc: "2.0",
          id,
          result: {
            content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
            structuredContent: Array.isArray(data) ? { items: data } : data,
          },
        };
      } catch (err) {
        // 도구 실행 오류는 프로토콜 오류가 아니라 결과(isError)로 돌려 모델이 읽고 대응하게 한다
        const message = err instanceof ToolError ? err.message : "도구 실행 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.";
        if (!(err instanceof ToolError)) console.error(`[mcp] ${tool.name} 실패:`, err);
        return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: message }], isError: true } };
      }
    }
    default:
      if (isNotification) return null; // notifications/initialized 등
      return rpcError(id, RPC.METHOD_NOT_FOUND, `Method not found: ${msg.method}`);
  }
}
