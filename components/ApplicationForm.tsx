"use client";

// components/ApplicationForm.tsx
// 숙소/크리에이터 신청 폼. 필드 정의(lib/applications)를 받아 렌더 → /api/applications 저장.

import { useEffect, useState, type FormEvent } from "react";
import { configFor, type ApplicationKind, type FieldDef } from "@/lib/applications";

type Values = Record<string, string | string[]>;

function initialValues(fields: FieldDef[]): Values {
  const v: Values = {};
  for (const f of fields) v[f.name] = f.type === "checkboxes" ? [] : "";
  return v;
}

const fieldBase =
  "w-full rounded-lg border border-ink/15 bg-white px-3.5 py-2.5 text-ink outline-none transition focus:border-film focus:ring-2 focus:ring-film/20";

export default function ApplicationForm({ kind }: { kind: ApplicationKind }) {
  const config = configFor(kind);
  const [values, setValues] = useState<Values>(() => initialValues(config.fields));
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState("");
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/status")
      .then((r) => r.json())
      .then((d: { submissionsEnabled?: boolean }) => {
        if (alive) setEnabled(Boolean(d.submissionsEnabled));
      })
      .catch(() => alive && setEnabled(true)); // 상태 확인 실패 시 폼은 열어두고 제출 단계에서 처리
    return () => {
      alive = false;
    };
  }, []);

  function set(name: string, value: string | string[]) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  function toggleCheckbox(name: string, option: string) {
    setValues((v) => {
      const cur = Array.isArray(v[name]) ? (v[name] as string[]) : [];
      const next = cur.includes(option) ? cur.filter((o) => o !== option) : [...cur, option];
      return { ...v, [name]: next };
    });
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/applications", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ kind, fields: values }),
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
      <div className="rounded-2xl border border-sage/40 bg-sage/10 px-6 py-10 text-center">
        <p className="text-lg font-black tracking-tight text-ink">신청이 접수됐어요 ✓</p>
        <p className="mt-2 font-serif text-sm text-ink/70">
          큐레이션 검토 후 영업일 기준 2~3일 내 이메일로 연락드릴게요.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      {enabled === false && (
        <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
          현재 온라인 접수가 일시적으로 비활성화되어 있어요. 잠시 후 다시 시도해 주세요.
        </p>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {config.fields.map((f) => (
          <div key={f.name} className={f.full || f.type === "checkboxes" || f.type === "textarea" ? "sm:col-span-2" : ""}>
            <label className="mb-1.5 block text-sm font-semibold text-ink/80">
              {f.label}
              {f.required && <span className="ml-0.5 text-film">*</span>}
            </label>

            {f.type === "textarea" ? (
              <textarea
                value={values[f.name] as string}
                onChange={(e) => set(f.name, e.target.value)}
                required={f.required}
                placeholder={f.placeholder}
                maxLength={f.maxLen}
                rows={4}
                className={`${fieldBase} resize-y`}
              />
            ) : f.type === "select" ? (
              <select
                value={values[f.name] as string}
                onChange={(e) => set(f.name, e.target.value)}
                required={f.required}
                className={fieldBase}
              >
                <option value="" disabled>
                  선택해 주세요
                </option>
                {f.options?.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : f.type === "checkboxes" ? (
              <div className="flex flex-wrap gap-2">
                {f.options?.map((o) => {
                  const active = (values[f.name] as string[]).includes(o);
                  return (
                    <button
                      type="button"
                      key={o}
                      onClick={() => toggleCheckbox(f.name, o)}
                      className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition ${
                        active
                          ? "border-film bg-film text-on-orange"
                          : "border-ink/20 bg-white text-ink/70 hover:border-ink/40"
                      }`}
                    >
                      {o}
                    </button>
                  );
                })}
              </div>
            ) : (
              <input
                type={f.type}
                value={values[f.name] as string}
                onChange={(e) => set(f.name, e.target.value)}
                required={f.required}
                placeholder={f.placeholder}
                maxLength={f.maxLen}
                className={fieldBase}
              />
            )}
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-film">{error}</p>}

      <button
        type="submit"
        disabled={status === "loading"}
        className="w-full rounded-xl bg-film px-6 py-3.5 font-bold text-on-orange shadow-sm transition hover:brightness-110 disabled:opacity-50"
      >
        {status === "loading" ? "접수 중…" : config.cta}
      </button>
      <p className="text-center font-mono text-xs text-ink/40">
        제출 시 캠페인 안내·연락 목적의 정보 수집에 동의하는 것으로 간주됩니다.
      </p>
    </form>
  );
}
