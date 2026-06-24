"use client";

// components/workspace/Workspace.tsx — 새 발행 워크스페이스 (스펙 §10):
// 컨피규레이터(좌) + 메인(우): 빈 상태 → 진행(폴링) → 결과(코어+채널 탭). 생성 플로우 상태머신.

import { useCallback, useEffect, useState } from "react";
import { WALLET_REFRESH_EVENT } from "@/components/shell/CreditBadge";
import type { Channel, Core } from "@/lib/multipublish/types";
import type { ClientGeneration } from "@/lib/multipublish/serialize";
import Configurator, { type GenerateConfig } from "./Configurator";
import ResultPanel from "./ResultPanel";

const POLL_MS = 2500;

export default function Workspace() {
  const [balance, setBalance] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [generation, setGeneration] = useState<ClientGeneration | null>(null);
  const [regeneratingChannel, setRegeneratingChannel] = useState<Channel | null>(null);
  const [error, setError] = useState("");

  const loadBalance = useCallback(async () => {
    try {
      const res = await fetch("/api/wallet", { cache: "no-store" });
      if (res.ok) setBalance((await res.json()).balance ?? null);
    } catch {
      /* 보조 정보 */
    }
  }, []);

  useEffect(() => {
    // 마운트 시 잔액 로드(클라이언트 fetch). setState는 fetch 이후(즉시 아님).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadBalance();
  }, [loadBalance]);

  // 폴링: 생성 요청 후 상태가 terminal 될 때까지 2.5초 간격 조회.
  useEffect(() => {
    if (!generationId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      if (stop) return;
      try {
        const res = await fetch(`/api/generations/${generationId}`, { cache: "no-store" });
        if (res.ok) {
          const g: ClientGeneration = (await res.json()).generation;
          setGeneration(g);
          if (g.status === "done" || g.status === "partial" || g.status === "failed") {
            stop = true;
            window.dispatchEvent(new Event(WALLET_REFRESH_EVENT));
            void loadBalance();
            return;
          }
        }
      } catch {
        /* 다음 틱에 재시도 */
      }
      timer = setTimeout(tick, POLL_MS);
    }
    void tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [generationId, loadBalance]);

  async function onSubmit(cfg: GenerateConfig) {
    setSubmitting(true);
    setError("");
    setGeneration(null);
    setGenerationId(null);
    try {
      const res = await fetch("/api/generations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(cfg),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data?.error ?? "생성 요청에 실패했어요.");
        return;
      }
      setGenerationId(data.generationId);
    } catch {
      setError("네트워크 오류가 발생했어요. 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onRegenerate(channel: Channel, editedCore: Core) {
    if (!generationId) return;
    setRegeneratingChannel(channel);
    setError("");
    try {
      const res = await fetch(`/api/generations/${generationId}/channels/${channel}/regenerate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ core: editedCore }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data?.error ?? "재생성에 실패했어요.");
        return;
      }
      const g = await fetch(`/api/generations/${generationId}`, { cache: "no-store" });
      if (g.ok) setGeneration((await g.json()).generation);
      window.dispatchEvent(new Event(WALLET_REFRESH_EVENT));
      void loadBalance();
    } catch {
      setError("네트워크 오류가 발생했어요.");
    } finally {
      setRegeneratingChannel(null);
    }
  }

  const status = generation?.status ?? (submitting || generationId ? "queued" : "idle");
  const terminal = status === "done" || status === "partial" || status === "failed";

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <Configurator balance={balance} submitting={submitting} onSubmit={onSubmit} />

      <div className="min-w-0">
        {error && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {status === "idle" && <EmptyState />}

        {(status === "queued" || status === "processing") && !terminal && (
          <ProgressView status={status} generation={generation} />
        )}

        {terminal && generation && (
          <>
            {generation.status === "partial" && (
              <Banner tone="amber">일부 채널 생성에 실패했어요. 실패한 탭에서 다시 시도할 수 있어요.</Banner>
            )}
            {generation.status === "failed" && (
              <Banner tone="red">생성에 실패했어요. {generation.error ?? ""}</Banner>
            )}
            <ResultPanel key={generation.id} generation={generation} regeneratingChannel={regeneratingChannel} onRegenerate={onRegenerate} />
          </>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="flex min-h-[320px] items-center justify-center rounded-2xl border border-stone-200 bg-white p-8 text-center">
      <div>
        <div className="text-4xl">🐻</div>
        <p className="mt-3 font-semibold">아직 만든 글이 없어요</p>
        <p className="mt-1 text-sm text-stone-500">왼쪽에서 키워드를 넣고 <b>생성</b>을 누르면 여기에 결과가 나타나요.</p>
      </div>
    </section>
  );
}

const STAGE_LABEL: Record<string, string> = {
  queued: "대기열에 넣는 중…",
  processing: "스크랩 → 코어 추출 → 채널 생성 중…",
};

function ProgressView({ status, generation }: { status: string; generation: ClientGeneration | null }) {
  return (
    <section className="flex min-h-[320px] items-center justify-center rounded-2xl border border-stone-200 bg-white p-8 text-center">
      <div>
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-emerald-200 border-t-emerald-600" />
        <p className="mt-4 font-semibold">곰대리가 만드는 중이에요</p>
        <p className="mt-1 text-sm text-stone-500">{STAGE_LABEL[status] ?? "처리 중…"}</p>
        {generation?.core && <p className="mt-2 text-xs text-emerald-700">코어 추출 완료 · 채널 생성 중</p>}
      </div>
    </section>
  );
}

function Banner({ tone, children }: { tone: "amber" | "red"; children: React.ReactNode }) {
  const cls = tone === "amber" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-red-200 bg-red-50 text-red-700";
  return <div className={`mb-4 rounded-xl border px-4 py-3 text-sm ${cls}`}>{children}</div>;
}
