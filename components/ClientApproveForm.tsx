"use client";

// components/ClientApproveForm.tsx  [신규 — P2 대행사 모드]
// 승인 링크 페이지의 승인 폼: 승인자 이름 + 확인 체크 → /api/approve/[token] → 게시 완료 안내.

import { useState } from "react";

export default function ClientApproveForm({ token, disabled }: { token: string; disabled: boolean }) {
  const [name, setName] = useState("");
  const [checked, setChecked] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");

  async function approve() {
    setStatus("loading");
    setError("");
    try {
      const res = await fetch(`/api/approve/${token}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim(), approved: true }),
      });
      const data = (await res.json().catch(() => ({}))) as { url?: string; error?: string };
      if (!res.ok) throw new Error(data.error || "승인 처리에 실패했어요.");
      setUrl(data.url ?? "");
      setStatus("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "승인 처리에 실패했어요.");
      setStatus("idle");
    }
  }

  if (status === "done") {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-800">
        <p className="font-semibold">승인했고, 페이지가 게시됐어요.</p>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block break-all underline">
            {url}
          </a>
        )}
      </div>
    );
  }

  const canSubmit = !disabled && name.trim().length > 0 && checked && status !== "loading";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
      <label className="block">
        <span className="mb-1 block font-medium text-slate-700">승인하시는 분 성함</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={40}
          placeholder="예) 홍길동 (OO카페 대표)"
          disabled={disabled}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-indigo-400 disabled:bg-slate-50"
        />
      </label>
      <label className="mt-4 flex items-start gap-2 font-medium">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} disabled={disabled} className="mt-0.5" />
        <span>아래 페이지 내용을 확인했고, 사실과 다르거나 지어낸 내용(후기·수치·자격)이 없습니다. 광고주로서 게시를 승인합니다.</span>
      </label>
      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-red-700">{error}</p>}
      <button
        onClick={approve}
        disabled={!canSubmit}
        className="mt-4 w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-40"
      >
        {status === "loading" ? "처리 중…" : "승인하고 게시"}
      </button>
    </div>
  );
}
