"use client";

// components/workspace/ResultPanel.tsx — 생성 후 결과 (스펙 §10):
// 코어 미리보기(수정 가능) + 채널 탭(블로그/스레드/인스타/카페/쇼츠) + [복사] + [이 채널 재생성·2P]

import { useMemo, useState } from "react";
import { POINTS } from "@/lib/config/points";
import { CHANNEL_LABEL, type Channel, type Core } from "@/lib/multipublish/types";
import type { ClientGeneration } from "@/lib/multipublish/serialize";
import { channelToCopyText } from "@/lib/multipublish/format";
import ChannelContentView from "./ChannelContentView";
import CopyButton from "./CopyButton";

export default function ResultPanel({
  generation,
  regeneratingChannel,
  onRegenerate,
}: {
  generation: ClientGeneration;
  regeneratingChannel: Channel | null;
  onRegenerate: (channel: Channel, editedCore: Core) => void;
}) {
  const channels = generation.channels;
  // 상태는 props에서 초기화. 생성이 바뀌면 부모가 key={generation.id}로 리마운트하여 리셋(effect 불필요).
  const [active, setActive] = useState<Channel>(channels[0]?.channel ?? "blog");
  const [msg, setMsg] = useState(generation.core?.core_message ?? "");
  const [reader, setReader] = useState(generation.core?.target_reader ?? "");
  const [tone, setTone] = useState(generation.core?.tone ?? "");
  const [anglesText, setAnglesText] = useState((generation.core?.angles ?? []).join("\n"));

  const editedCore: Core | null = useMemo(() => {
    if (!generation.core) return null;
    return {
      ...generation.core,
      core_message: msg,
      target_reader: reader,
      tone,
      angles: anglesText.split("\n").map((s) => s.trim()).filter(Boolean),
    };
  }, [generation.core, msg, reader, tone, anglesText]);

  const activeOut = channels.find((c) => c.channel === active);

  return (
    <div className="space-y-5">
      {/* 코어 미리보기(수정 가능) */}
      {generation.core && (
        <section className="rounded-2xl border border-stone-200 bg-white p-5">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="font-bold">코어</h2>
            <span className="text-xs text-stone-400">수정하고 채널을 재생성하면 반영돼요</span>
          </div>
          <label className="block">
            <span className="text-xs font-semibold text-stone-500">핵심 메시지</span>
            <textarea value={msg} onChange={(e) => setMsg(e.target.value)} rows={2}
              className="mt-1 w-full resize-y rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-emerald-400" />
          </label>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-semibold text-stone-500">대상 독자</span>
              <input value={reader} onChange={(e) => setReader(e.target.value)}
                className="mt-1 w-full rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-emerald-400" />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-stone-500">톤</span>
              <input value={tone} onChange={(e) => setTone(e.target.value)}
                className="mt-1 w-full rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-emerald-400" />
            </label>
          </div>
          <label className="mt-3 block">
            <span className="text-xs font-semibold text-stone-500">앵글 (줄바꿈으로 구분)</span>
            <textarea value={anglesText} onChange={(e) => setAnglesText(e.target.value)} rows={3}
              className="mt-1 w-full resize-y rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-emerald-400" />
          </label>
          {generation.core.facts.length > 0 && (
            <div className="mt-3">
              <span className="text-xs font-semibold text-stone-500">사실(facts) · 출처 포함</span>
              <ul className="mt-1 space-y-1">
                {generation.core.facts.map((f, i) => (
                  <li key={i} className="text-sm text-stone-600">
                    • {f.claim} <a href={f.source} target="_blank" rel="noreferrer" className="text-emerald-700 underline">[출처]</a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* 채널 탭 */}
      <section className="rounded-2xl border border-stone-200 bg-white">
        <div className="flex flex-wrap gap-1 border-b border-stone-200 p-2">
          {channels.map((c) => (
            <button
              key={c.channel}
              onClick={() => setActive(c.channel)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                active === c.channel ? "bg-emerald-50 text-emerald-800" : "text-stone-500 hover:bg-stone-50"
              }`}
            >
              {CHANNEL_LABEL[c.channel]}
              {c.status === "failed" && <span className="ml-1 text-red-500">!</span>}
            </button>
          ))}
        </div>

        <div className="p-5">
          {!activeOut ? (
            <p className="text-sm text-stone-400">선택한 채널 결과가 없어요.</p>
          ) : activeOut.status === "failed" ? (
            <div className="text-center">
              <p className="text-sm text-red-600">이 채널 생성에 실패했어요.</p>
              {activeOut.error && <p className="mt-1 text-xs text-stone-400">{activeOut.error}</p>}
              <button
                onClick={() => editedCore && onRegenerate(active, editedCore)}
                disabled={regeneratingChannel === active}
                className="mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
              >
                {regeneratingChannel === active ? "재생성 중…" : `다시 시도 · ${POINTS.CHANNEL_REGEN}P`}
              </button>
            </div>
          ) : (
            <>
              <div className="mb-3 flex items-center justify-end gap-2">
                <CopyButton text={channelToCopyText(active, activeOut.content)} />
                <button
                  onClick={() => editedCore && onRegenerate(active, editedCore)}
                  disabled={regeneratingChannel === active}
                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800 transition hover:bg-emerald-100 disabled:opacity-50"
                >
                  {regeneratingChannel === active ? "재생성 중…" : `이 채널 재생성 · ${POINTS.CHANNEL_REGEN}P`}
                </button>
              </div>
              <ChannelContentView channel={active} content={activeOut.content} />
            </>
          )}
        </div>
      </section>
    </div>
  );
}
