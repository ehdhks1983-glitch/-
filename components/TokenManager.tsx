"use client";

// components/TokenManager.tsx  [신규 — P2 MCP 연동]
// 개인 액세스 토큰 발급·폐기. 발급한 원문 토큰은 이 화면에서 한 번만 보여 준다.

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ApiTokenRow } from "@/lib/db/apiTokens";

export default function TokenManager({ tokens, endpoint }: { tokens: ApiTokenRow[]; endpoint: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [issued, setIssued] = useState("");
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function issue() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/tokens", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      const data = (await res.json().catch(() => ({}))) as { token?: string; error?: string };
      if (!res.ok || !data.token) throw new Error(data.error || "발급에 실패했어요.");
      setIssued(data.token);
      setName("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "발급에 실패했어요.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    if (!confirm("이 토큰을 폐기할까요? 이 토큰을 쓰는 AI 비서는 더 이상 연결되지 않아요.")) return;
    const res = await fetch(`/api/tokens/${id}`, { method: "DELETE" });
    if (res.ok) router.refresh();
    else setError("폐기에 실패했어요.");
  }

  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      // clipboard 불가 환경 무시
    }
  }

  const command = `claude mcp add --transport http promptsite ${endpoint} --header "Authorization: Bearer ${issued || "<토큰>"}"`;
  const active = tokens.filter((t) => !t.revoked_at);

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold">액세스 토큰</h2>
        <p className="mt-1 text-sm text-slate-500">AI 비서마다 따로 발급하면 하나만 끊을 수 있어요. 최대 5개.</p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="이름 (예: Claude, ChatGPT)"
            maxLength={60}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
          <button
            onClick={issue}
            disabled={busy}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {busy ? "발급 중…" : "토큰 발급"}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        {issued && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm">
            <p className="font-semibold text-amber-900">지금만 볼 수 있어요. 안전한 곳에 복사해 두세요.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 break-all rounded bg-white px-2 py-1.5 text-xs">{issued}</code>
              <button
                onClick={() => copy(issued, "token")}
                className="shrink-0 rounded-md border border-amber-300 bg-white px-2 py-1 text-xs font-medium"
              >
                {copied === "token" ? "복사됨!" : "복사"}
              </button>
            </div>
          </div>
        )}

        {active.length > 0 && (
          <ul className="mt-4 divide-y divide-slate-100 text-sm">
            {active.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <p className="font-medium">{t.name || "이름 없음"}</p>
                  <p className="text-xs text-slate-400">
                    {t.prefix}… · 발급 {new Date(t.created_at).toLocaleDateString("ko-KR")} · 마지막 사용{" "}
                    {t.last_used_at ? new Date(t.last_used_at).toLocaleString("ko-KR") : "없음"}
                  </p>
                </div>
                <button
                  onClick={() => revoke(t.id)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-50"
                >
                  폐기
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
        <h2 className="font-semibold">연결 방법</h2>
        <p className="mt-2 text-slate-600">MCP 주소</p>
        <div className="mt-1 flex items-center gap-2">
          <code className="flex-1 break-all rounded bg-slate-50 px-2 py-1.5 text-xs">{endpoint}</code>
          <button onClick={() => copy(endpoint, "endpoint")} className="shrink-0 rounded-md border border-slate-200 px-2 py-1 text-xs">
            {copied === "endpoint" ? "복사됨!" : "복사"}
          </button>
        </div>
        <p className="mt-4 text-slate-600">Claude Code 에서 연결</p>
        <div className="mt-1 flex items-start gap-2">
          <code className="flex-1 break-all rounded bg-slate-50 px-2 py-1.5 text-xs">{command}</code>
          <button onClick={() => copy(command, "cmd")} className="shrink-0 rounded-md border border-slate-200 px-2 py-1 text-xs">
            {copied === "cmd" ? "복사됨!" : "복사"}
          </button>
        </div>
        <p className="mt-4 text-slate-600">
          그 밖의 MCP 지원 앱은 위 주소를 ‘HTTP(Streamable HTTP)’ 서버로 추가하고, 헤더에{" "}
          <code className="rounded bg-slate-50 px-1">Authorization: Bearer 토큰</code> 을 넣으면 됩니다.
        </p>
        <ul className="mt-4 list-disc space-y-1 pl-5 text-slate-600">
          <li>쓸 수 있는 일: 광고 문구 검사, 내 페이지 목록·성과 보기, 랜딩페이지 초안 만들기</li>
          <li>AI 비서는 게시(공개)를 할 수 없어요. 초안은 이 사이트에서 검사 결과를 확인하고 승인해야 공개됩니다.</li>
          <li>신청자 이메일 같은 개인정보는 AI 비서에 넘기지 않습니다.</li>
        </ul>
      </section>
    </div>
  );
}
