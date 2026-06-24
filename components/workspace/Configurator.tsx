"use client";

// components/workspace/Configurator.tsx — 컨피규레이터 (스펙 §10):
// 키워드(필수) · 참고 URL(복수) · 톤 슬라이더 · 수익화 토글 · 채널 선택 · [생성 · 10P](잔액 부족 시 비활성)

import { useState } from "react";
import { POINTS } from "@/lib/config/points";
import { ALL_CHANNELS, CHANNEL_LABEL, type Channel } from "@/lib/multipublish/types";

export interface GenerateConfig {
  keyword: string;
  sourceUrls: string[];
  options: { tone: number; monetize: boolean; channels: Channel[] };
}

export default function Configurator({
  balance,
  submitting,
  onSubmit,
}: {
  balance: number | null;
  submitting: boolean;
  onSubmit: (cfg: GenerateConfig) => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [urls, setUrls] = useState<string[]>([""]);
  const [tone, setTone] = useState(50);
  const [monetize, setMonetize] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([...ALL_CHANNELS]);

  const insufficient = balance !== null && balance < POINTS.SET;
  const canSubmit = keyword.trim().length > 0 && channels.length > 0 && !submitting && !insufficient;

  function toggleChannel(c: Channel) {
    setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }
  function setUrl(i: number, v: string) {
    setUrls((prev) => prev.map((u, idx) => (idx === i ? v : u)));
  }

  function submit() {
    if (!canSubmit) return;
    onSubmit({
      keyword: keyword.trim(),
      sourceUrls: urls.map((u) => u.trim()).filter(Boolean),
      options: { tone, monetize, channels },
    });
  }

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5">
      <h1 className="text-lg font-bold">새 발행</h1>
      <p className="mt-1 text-sm text-stone-500">키워드와 참고자료로 블로그 + 4채널을 한 번에.</p>

      <div className="mt-4 space-y-4">
        {/* 키워드 */}
        <label className="block">
          <span className="mb-1 block text-sm font-semibold">키워드 <span className="text-emerald-600">*</span></span>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="예: 곰탕 끓이는 법"
            className="w-full rounded-lg border border-stone-200 px-3 py-2.5 outline-none focus:border-emerald-400"
          />
        </label>

        {/* 참고 URL (복수) */}
        <div>
          <span className="mb-1 block text-sm font-semibold">참고 URL <span className="text-stone-400">(선택)</span></span>
          <div className="space-y-2">
            {urls.map((u, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={u}
                  onChange={(e) => setUrl(i, e.target.value)}
                  placeholder="https://..."
                  className="min-w-0 flex-1 rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-emerald-400"
                />
                {urls.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setUrls((p) => p.filter((_, idx) => idx !== i))}
                    className="shrink-0 rounded-lg border border-stone-200 px-2.5 text-stone-400 hover:bg-stone-50"
                    aria-label="삭제"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
          {urls.length < 5 && (
            <button
              type="button"
              onClick={() => setUrls((p) => [...p, ""])}
              className="mt-2 text-sm font-medium text-emerald-700 hover:underline"
            >
              + 참고 URL 추가
            </button>
          )}
        </div>

        {/* 톤 슬라이더 */}
        <div>
          <div className="mb-1 flex items-center justify-between text-sm font-semibold">
            <span>톤</span>
            <span className="text-xs font-normal text-stone-400">{tone <= 33 ? "정중/전문" : tone <= 66 ? "균형" : "캐주얼/친근"}</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={tone}
            onChange={(e) => setTone(Number(e.target.value))}
            className="w-full accent-emerald-600"
          />
        </div>

        {/* 수익화 토글 */}
        <label className="flex cursor-pointer items-center justify-between rounded-lg border border-stone-200 px-3 py-2.5">
          <span className="text-sm font-semibold">수익화 톤 <span className="font-normal text-stone-400">(전환 유도)</span></span>
          <input type="checkbox" checked={monetize} onChange={(e) => setMonetize(e.target.checked)} className="h-4 w-4 accent-emerald-600" />
        </label>

        {/* 채널 선택 */}
        <div>
          <span className="mb-1.5 block text-sm font-semibold">채널</span>
          <div className="flex flex-wrap gap-2">
            {ALL_CHANNELS.map((c) => {
              const on = channels.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() => toggleChannel(c)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                    on ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-stone-200 text-stone-500 hover:bg-stone-50"
                  }`}
                >
                  {CHANNEL_LABEL[c]}
                </button>
              );
            })}
          </div>
        </div>

        {/* 생성 버튼 */}
        <button
          onClick={submit}
          disabled={!canSubmit}
          className="w-full rounded-xl bg-emerald-600 px-4 py-3 font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "생성 요청 중…" : `생성 · ${POINTS.SET}P`}
        </button>
        {insufficient && (
          <p className="text-center text-sm text-red-600">
            크레딧이 부족해요 (보유 {balance}P). 충전 후 이용해 주세요.
          </p>
        )}
      </div>
    </section>
  );
}
