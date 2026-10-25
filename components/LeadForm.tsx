"use client";

// components/LeadForm.tsx  [신규]
// 공개 페이지 이메일 신청 폼. /api/leads 로 저장. 성공 시 완료 메시지로 전환.
// 개인정보 수집·이용 동의(필수)를 받아야 제출된다 — 서버도 동의 여부를 다시 확인한다.

import { useState, type FormEvent } from "react";
import { consentText, leadConsentItems } from "@/lib/compliance/privacy";
import type { PageLang } from "@/lib/i18n/langs";
import { uiText } from "@/lib/i18n/ui";
import { detectSource, sourceStorageKey } from "@/lib/analytics/source";

/** 방문 집계(ViewTracker)가 남긴 유입 경로. 없으면 지금 판별. */
function currentSource(projectId: string): string {
  try {
    const saved = sessionStorage.getItem(sourceStorageKey(projectId));
    if (saved) return saved;
  } catch {
    // sessionStorage 불가 → 아래에서 판별
  }
  return detectSource(document.referrer, location.search, navigator.userAgent, location.hostname);
}

export default function LeadForm({
  projectId,
  buttonLabel,
  operator = "",
  lang = "ko",
}: {
  projectId: string;
  buttonLabel?: string;
  /** 동의 고지의 '수집하는 곳'(브랜드명). */
  operator?: string;
  /** 외국인 손님용 페이지 언어 — 폼 문구와 동의 고지를 같은 언어로 보여 준다. */
  lang?: PageLang;
}) {
  const t = uiText(lang).signup;
  const consentT = consentText(lang);
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!consent) {
      setError(consentT.required);
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/leads", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ projectId, email: email.trim(), consent, source: currentSource(projectId) }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      // 서버 오류 문구는 한국어라, 외국어 페이지에서는 같은 언어의 일반 안내로 바꿔 보여 준다
      if (!res.ok) throw new Error(lang === "ko" ? data?.error || t.failed : t.failed);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : t.failed);
      setStatus("idle");
    }
  }

  if (status === "done") {
    return (
      <div className="mx-auto max-w-md rounded-xl bg-white/10 px-6 py-5 text-center text-white">
        {t.done}
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
          placeholder={t.email}
          maxLength={254}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none focus:border-indigo-400"
        />
        <button
          type="submit"
          disabled={status === "loading"}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {status === "loading" ? t.submitting : buttonLabel || t.submit}
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
          <span>{consentT.label}</span>
        </label>
        <dl className="mt-2 space-y-0.5 pl-5">
          {leadConsentItems(operator, lang).map((i) => (
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
