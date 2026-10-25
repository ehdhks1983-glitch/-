"use client";

// components/StoreBar.tsx  [신규 — P2 여러 매장]
// 대시보드 매장 필터(전체·매장별·미지정) + 매장 추가·삭제.

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { StoreRow } from "@/lib/db/stores";

export default function StoreBar({ stores, current }: { stores: StoreRow[]; current: string }) {
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function add() {
    setError("");
    const res = await fetch("/api/stores", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    const data = (await res.json().catch(() => ({}))) as { store?: StoreRow; error?: string };
    if (!res.ok || !data.store) {
      setError(data.error || "매장 추가에 실패했어요.");
      return;
    }
    setName("");
    setAdding(false);
    router.push(`/dashboard?store=${data.store.id}`);
    router.refresh();
  }

  async function remove(store: StoreRow) {
    if (!confirm(`'${store.name}' 매장을 삭제할까요? 소속 페이지는 지워지지 않고 '매장 미지정'으로 옮겨져요.`)) return;
    const res = await fetch(`/api/stores/${store.id}`, { method: "DELETE" });
    if (!res.ok) {
      setError("삭제에 실패했어요.");
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  const chip = (active: boolean) =>
    "rounded-full border px-3 py-1.5 text-sm transition " +
    (active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white hover:border-slate-400");
  const currentStore = stores.find((s) => s.id === current);

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link href="/dashboard" className={chip(current === "all")}>
          전체
        </Link>
        {stores.map((s) => (
          <Link key={s.id} href={`/dashboard?store=${s.id}`} className={chip(current === s.id)}>
            {s.name}
          </Link>
        ))}
        {stores.length > 0 && (
          <Link href="/dashboard?store=none" className={chip(current === "none")}>
            매장 미지정
          </Link>
        )}
        {adding ? (
          <span className="flex items-center gap-1">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && name.trim() && add()}
              maxLength={40}
              placeholder="매장 이름"
              className="w-32 rounded-full border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-indigo-400"
            />
            <button onClick={add} disabled={!name.trim()} className="rounded-full bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40">
              추가
            </button>
            <button onClick={() => setAdding(false)} className="px-2 text-sm text-slate-500">
              취소
            </button>
          </span>
        ) : (
          <button onClick={() => setAdding(true)} className="rounded-full border border-dashed border-slate-300 px-3 py-1.5 text-sm text-slate-500 hover:border-slate-400">
            + 매장
          </button>
        )}
        {currentStore && (
          <button onClick={() => remove(currentStore)} className="ml-auto text-xs text-slate-400 hover:text-red-600">
            이 매장 삭제
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
