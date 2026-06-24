"use client";

// components/workspace/LibraryList.tsx — 내 발행물 목록 (스펙 §10/§15.10).
// 제목·키워드·날짜·상태 → 클릭 시 결과 재열람(detail).

import { useEffect, useState } from "react";
import Link from "next/link";
import type { ClientGenerationSummary } from "@/lib/multipublish/serialize";
import type { GenerationStatus } from "@/lib/multipublish/types";

const STATUS: Record<GenerationStatus, { label: string; cls: string }> = {
  queued: { label: "대기", cls: "bg-stone-100 text-stone-600" },
  processing: { label: "생성 중", cls: "bg-blue-50 text-blue-700" },
  done: { label: "완료", cls: "bg-emerald-50 text-emerald-700" },
  partial: { label: "일부 완료", cls: "bg-amber-50 text-amber-700" },
  failed: { label: "실패", cls: "bg-red-50 text-red-700" },
};

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export default function LibraryList() {
  const [items, setItems] = useState<ClientGenerationSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // 마운트 시 목록 로드(클라이언트 fetch). setState는 응답 후.
    void (async () => {
      try {
        const res = await fetch("/api/generations", { cache: "no-store" });
        if (!res.ok) {
          setError(res.status === 401 ? "로그인이 필요해요." : "목록을 불러오지 못했어요.");
          return;
        }
        setItems((await res.json()).generations ?? []);
      } catch {
        setError("네트워크 오류가 발생했어요.");
      }
    })();
  }, []);

  return (
    <div>
      <h1 className="text-lg font-bold">내 발행물</h1>
      <p className="mt-1 text-sm text-stone-500">생성한 발행물을 모아보고 다시 열람할 수 있어요.</p>

      {error && <p className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      {!items && !error && <p className="mt-5 text-sm text-stone-400">불러오는 중…</p>}

      {items && items.length === 0 && (
        <div className="mt-5 rounded-2xl border border-dashed border-stone-300 bg-white p-10 text-center">
          <p className="text-sm text-stone-500">아직 발행물이 없어요.</p>
          <Link href="/workspace" className="mt-2 inline-block text-sm font-semibold text-emerald-700 hover:underline">
            새 발행 시작 →
          </Link>
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="mt-5 space-y-2">
          {items.map((g) => (
            <li key={g.id}>
              <Link
                href={`/workspace/library/${g.id}`}
                className="flex items-center justify-between gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 transition hover:border-emerald-300 hover:bg-emerald-50/30"
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold">
                    {g.starred && <span className="mr-1">⭐</span>}
                    {g.title || g.keyword}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-stone-400">
                    {g.keyword} · {g.channelCount}채널 · {fmtDate(g.created_at)}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS[g.status].cls}`}>
                  {STATUS[g.status].label}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
