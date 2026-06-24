"use client";

// components/workspace/GenerationDetail.tsx — 발행물 재열람 (스펙 §10/§15.10).
// GET /:id 로 결과를 불러와 ResultPanel 렌더 + 채널 재생성. 미완료면 폴링.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { WALLET_REFRESH_EVENT } from "@/components/shell/CreditBadge";
import type { Channel, Core } from "@/lib/multipublish/types";
import type { ClientGeneration } from "@/lib/multipublish/serialize";
import ResultPanel from "./ResultPanel";

export default function GenerationDetail({ id }: { id: string }) {
  const [generation, setGeneration] = useState<ClientGeneration | null>(null);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [regeneratingChannel, setRegeneratingChannel] = useState<Channel | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/generations/${id}`, { cache: "no-store" });
    if (res.status === 404) {
      setNotFound(true);
      return null;
    }
    if (!res.ok) {
      setError("불러오지 못했어요.");
      return null;
    }
    const g: ClientGeneration = (await res.json()).generation;
    setGeneration(g);
    return g;
  }, [id]);

  // 최초 로드 + 미완료면 폴링.
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      if (stop) return;
      const g = await load().catch(() => null);
      const terminal = !g || g.status === "done" || g.status === "partial" || g.status === "failed";
      if (!terminal) timer = setTimeout(tick, 2500);
    }
    void tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [load]);

  async function onRegenerate(channel: Channel, editedCore: Core) {
    setRegeneratingChannel(channel);
    setError("");
    try {
      const res = await fetch(`/api/generations/${id}/channels/${channel}/regenerate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ core: editedCore }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data?.error ?? "재생성에 실패했어요.");
        return;
      }
      await load();
      window.dispatchEvent(new Event(WALLET_REFRESH_EVENT));
    } catch {
      setError("네트워크 오류가 발생했어요.");
    } finally {
      setRegeneratingChannel(null);
    }
  }

  if (notFound) {
    return (
      <div className="rounded-2xl border border-stone-200 bg-white p-10 text-center">
        <p className="text-sm text-stone-500">발행물을 찾을 수 없어요.</p>
        <Link href="/workspace/library" className="mt-2 inline-block text-sm font-semibold text-emerald-700 hover:underline">
          ← 내 발행물로
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <Link href="/workspace/library" className="text-sm font-medium text-stone-500 hover:text-stone-800">
          ← 내 발행물
        </Link>
        {generation && <span className="text-sm font-semibold">{generation.title || generation.keyword}</span>}
      </div>

      {error && <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {!generation ? (
        <p className="text-sm text-stone-400">불러오는 중…</p>
      ) : generation.status === "queued" || generation.status === "processing" ? (
        <div className="rounded-2xl border border-stone-200 bg-white p-8 text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-emerald-200 border-t-emerald-600" />
          <p className="mt-3 text-sm text-stone-500">아직 생성 중이에요…</p>
        </div>
      ) : (
        <ResultPanel
          key={generation.id}
          generation={generation}
          regeneratingChannel={regeneratingChannel}
          onRegenerate={onRegenerate}
        />
      )}
    </div>
  );
}
