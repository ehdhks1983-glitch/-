"use client";

// components/DeleteProjectButton.tsx  [신규] — 확인 후 프로젝트 삭제, 목록 새로고침.

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function DeleteProjectButton({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function remove() {
    if (!window.confirm("이 페이지를 삭제할까요? 되돌릴 수 없어요.")) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        window.alert(data?.error || "삭제에 실패했어요.");
        return;
      }
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={remove}
      disabled={loading}
      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-50"
    >
      {loading ? "삭제 중…" : "삭제"}
    </button>
  );
}
