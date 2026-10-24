"use client";

// components/LeadForm.tsx  [신규]
// 공개 페이지 이메일 신청 폼. /api/leads 로 저장. 성공 시 완료 메시지로 전환.
// 개인정보 수집·이용 동의(필수)를 받아야 제출된다 — 서버도 동의 여부를 다시 확인한다.

import { useState, type FormEvent } from "react";
import { leadConsentItems } from "@/lib/compliance/privacy";

export default function LeadForm({
  projectId,
  buttonLabel = "신청하기",
  operator = "",
}: {
  projectId: string;
  buttonLabel?: string;
  /** 동의 고지의 '수집하는 곳'(브랜드명). */
  operator?: string;
}) {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!consent) {
      setError("개인정보 수집·이용에 동의해 주세요.");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/leads", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ projectId, email: email.trim(), consent }),
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
      <div className="mt-4 rounded-lg bg-white/5 px-4 py-3 text-left text-xs leading-5 text-slate-300">
        <label className="flex items-start gap-2 font-medium text-white">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            className="mt-0.5"
          />
          <span>[필수] 개인정보 수집·이용에 동의합니다.</span>
        </label>
        <dl className="mt-2 space-y-0.5 pl-5">
          {leadConsentItems(operator).map((i) => (
            <div key={i.label} className="flex gap-2">
              <dt className="shrink-0 text-slate-400">{i.label}</dt>
              <dd>{i.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      {error && <p className="mt-2 text-sm text-red-300">{error}</p>}
    </div>
  );
}
