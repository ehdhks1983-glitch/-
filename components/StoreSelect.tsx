"use client";

// components/StoreSelect.tsx  [신규 — P2 여러 매장] — 페이지의 소속 매장 지정(내용이 안 바뀌므로 게시 승인 불필요).

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { StoreRow } from "@/lib/db/stores";

export default function StoreSelect({ projectId, stores, value }: { projectId: string; stores: StoreRow[]; value: string | null }) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);

  async function change(next: string) {
    setSaving(true);
    const res = await fetch(`/api/projects/${projectId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ store_id: next || null }),
    });
    setSaving(false);
    if (res.ok) router.refresh();
  }

  return (
    <select
      aria-label="매장"
      value={value ?? ""}
      disabled={saving}
      onChange={(e) => change(e.target.value)}
      className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-600"
    >
      <option value="">매장 미지정</option>
      {stores.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}
