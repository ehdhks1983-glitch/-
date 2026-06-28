"use client";

// components/license/LicenseManager.tsx  [신규]
// 통합 라이선스 관리 UI(클라이언트). 발급 폼 + 코드 목록/작업.
// 모든 변경은 /api/admin/licenses* 로 보내고, 성공 시 목록을 다시 불러온다.

import { useState } from "react";
import type { BotMeta } from "@/lib/license/config";
import type { LicenseWithUsage } from "@/lib/license/db";

function fmtDate(iso: string | null): string {
  if (!iso) return "무기한";
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function fmtSeen(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function isExpired(l: LicenseWithUsage): boolean {
  return !!l.expires_at && new Date(l.expires_at).getTime() <= Date.now();
}

export default function LicenseManager({
  initialLicenses,
  botList,
}: {
  initialLicenses: LicenseWithUsage[];
  botList: BotMeta[];
}) {
  const [licenses, setLicenses] = useState<LicenseWithUsage[]>(initialLicenses);
  const [label, setLabel] = useState("");
  const [maxDevices, setMaxDevices] = useState(1);
  const [validDays, setValidDays] = useState(0); // 0 = 무기한
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  async function reload() {
    const res = await fetch("/api/admin/licenses", { cache: "no-store" });
    if (res.ok) {
      const data = (await res.json()) as { licenses: LicenseWithUsage[] };
      setLicenses(data.licenses);
    }
  }

  async function issue(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/admin/licenses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label,
          maxDevices,
          validDays: validDays > 0 ? validDays : null,
        }),
      });
      if (!res.ok) {
        const d = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(d.error ?? "발급에 실패했습니다.");
      }
      setLabel("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "발급에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function act(id: string, body: Record<string, unknown>, confirmMsg?: string) {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/admin/licenses/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(d.error ?? "변경에 실패했습니다.");
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "변경에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("정말 삭제할까요? 되돌릴 수 없고, 연결된 기기/로그도 함께 삭제됩니다.")) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/admin/licenses/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const d = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(d.error ?? "삭제에 실패했습니다.");
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(code);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      // 클립보드 권한 없을 때는 무시.
    }
  }

  return (
    <div className="space-y-8">
      {/* 안내 */}
      <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4 text-sm text-indigo-900">
        <p className="font-semibold">올인원 라이선스</p>
        <p className="mt-1 text-indigo-700">
          코드 1개로 아래 {botList.length}개 봇을 모두 사용합니다. 봇은 실행 시 서버에 코드를 검증합니다.
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {botList.map((b) => (
            <span key={b.id} className="rounded-full bg-white px-2.5 py-0.5 text-xs font-medium text-indigo-700">
              {b.name}
            </span>
          ))}
        </div>
      </div>

      {/* 발급 폼 */}
      <form onSubmit={issue} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">새 코드 발급</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className="block sm:col-span-1">
            <span className="mb-1 block text-sm font-medium text-slate-700">라벨 / 고객명</span>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="예: 홍길동 / 카카오 채널"
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 outline-none focus:border-indigo-400"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">허용 기기 수</span>
            <input
              type="number"
              min={1}
              max={999}
              value={maxDevices}
              onChange={(e) => setMaxDevices(Math.max(1, Number(e.target.value) || 1))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 outline-none focus:border-indigo-400"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">유효기간(일, 0=무기한)</span>
            <input
              type="number"
              min={0}
              value={validDays}
              onChange={(e) => setValidDays(Math.max(0, Number(e.target.value) || 0))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 outline-none focus:border-indigo-400"
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={busy}
          className="mt-4 rounded-full bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {busy ? "처리 중…" : "+ 코드 발급"}
        </button>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </form>

      {/* 목록 */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-bold">발급된 코드 ({licenses.length})</h2>
          <button onClick={reload} disabled={busy} className="text-sm text-slate-500 hover:text-slate-800">
            새로고침
          </button>
        </div>
        {licenses.length === 0 ? (
          <p className="px-6 py-12 text-center text-slate-500">아직 발급된 코드가 없어요.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-3 font-medium">코드 / 라벨</th>
                  <th className="px-4 py-3 font-medium">상태</th>
                  <th className="px-4 py-3 font-medium">기기</th>
                  <th className="px-4 py-3 font-medium">만료</th>
                  <th className="px-4 py-3 font-medium">최근 사용</th>
                  <th className="px-4 py-3 font-medium">작업</th>
                </tr>
              </thead>
              <tbody>
                {licenses.map((l) => {
                  const expired = isExpired(l);
                  return (
                    <tr key={l.id} className="border-b border-slate-50 align-top">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <code className="rounded bg-slate-100 px-2 py-1 font-mono text-[13px]">{l.code}</code>
                          <button
                            onClick={() => copyCode(l.code)}
                            className="text-xs text-indigo-600 hover:underline"
                            title="코드 복사"
                          >
                            {copied === l.code ? "복사됨" : "복사"}
                          </button>
                        </div>
                        {l.label && <div className="mt-1 text-xs text-slate-500">{l.label}</div>}
                      </td>
                      <td className="px-4 py-3">
                        {l.status === "revoked" ? (
                          <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700">정지</span>
                        ) : expired ? (
                          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">만료</span>
                        ) : (
                          <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700">활성</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600">
                        {l.devices_used} / {l.max_devices}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDate(l.expires_at)}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-500">{fmtSeen(l.last_seen_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2 text-xs">
                          {l.status === "revoked" ? (
                            <button onClick={() => act(l.id, { action: "activate" })} disabled={busy} className="text-emerald-600 hover:underline">
                              재개
                            </button>
                          ) : (
                            <button onClick={() => act(l.id, { action: "revoke" }, "이 코드를 정지할까요? 봇에서 즉시 인증이 막힙니다.")} disabled={busy} className="text-amber-600 hover:underline">
                              정지
                            </button>
                          )}
                          <button onClick={() => act(l.id, { action: "reset-devices" }, "기기 바인딩을 초기화할까요? 다음 실행부터 다시 등록됩니다.")} disabled={busy} className="text-slate-600 hover:underline">
                            기기초기화
                          </button>
                          <button onClick={() => remove(l.id)} disabled={busy} className="text-red-600 hover:underline">
                            삭제
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
