"use client";

// components/LeadForm.tsx  [신규]
// 공개 페이지 이메일 신청 폼. /api/leads 로 저장. 성공 시 완료 메시지로 전환.

import { useState, type FormEvent } from "react";

export default function LeadForm({
  projectId,
  buttonLabel = "신청하기",
}: {
  projectId: string;
  buttonLabel?: string;
}) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/leads", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ projectId, email: email.trim() }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) throw new Error(data?.error || "신청에 실패했어요. 잠시 후 다시 시도해 주세요.");
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "신청에 실패했어요.");
      setStatus("idle");
    }
  }

  if (status === "done") {
    return (
      <div className="mx-auto max-w-md rounded-xl bg-white/10 px-6 py-5 text-center text-white">
        신청이 접수됐어요. 곧 연락드릴게요! 🎉
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="이메일 주소"
          maxLength={254}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none focus:border-indigo-400"
        />
        <button
          type="submit"
          disabled={status === "loading"}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {status === "loading" ? "신청 중…" : buttonLabel}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red-300">{error}</p>}
    </div>
  );
}
