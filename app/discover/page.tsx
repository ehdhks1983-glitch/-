"use client";

// app/discover/page.tsx  [신규]
// 아이디어 발굴 화면 — 블로그봇 "키워드 발굴 탭"의 등가물(새 창 아님, 새 라우트).
// 시드 입력 → [발굴 시작] → 결과표(체크박스·아이디어·적합도·근거) → [선택 대기열에 추가].
// 발굴은 /api/discover(별도 네트워크 호출)이며 UI는 비동기로 멈추지 않는다.

import { useEffect, useState } from "react";
import Link from "next/link";
import { addIdeas, loadQueue, type DiscoveredIdea } from "@/lib/queue/queue";

interface AppStatus {
  mock: boolean;
  supabaseConfigured: boolean;
}

const EXAMPLE_SEEDS = ["온라인 코칭/클래스", "동네 카페·디저트", "B2B SaaS 도구", "소상공인 마케팅 대행"];

export default function DiscoverPage() {
  const [seed, setSeed] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ideas, setIdeas] = useState<DiscoveredIdea[]>([]);
  const [usedSeed, setUsedSeed] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [addedMsg, setAddedMsg] = useState("");
  const [queueCount, setQueueCount] = useState(0);
  const [status, setStatus] = useState<AppStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await Promise.resolve(); // effect 본문 동기 setState 회피(set-state-in-effect 규칙)
      if (cancelled) return;
      setQueueCount(loadQueue().length);
      try {
        const s = (await fetch("/api/status").then((r) => r.json())) as AppStatus;
        if (!cancelled) setStatus(s);
      } catch {
        /* 상태 조회 실패는 무시 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onDiscover() {
    if (!seed.trim()) {
      setError("어떤 주제로 아이디어를 찾을지 적어 주세요.");
      return;
    }
    setError("");
    setAddedMsg("");
    setLoading(true);
    try {
      const res = await fetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed: seed.trim() }),
      });
      const data = (await res.json().catch(() => ({}))) as { ideas?: DiscoveredIdea[]; error?: string };
      if (!res.ok) throw new Error(data?.error || "발굴에 실패했어요. 잠시 후 다시 시도해 주세요.");
      setIdeas(data.ideas ?? []);
      setUsedSeed(seed.trim());
      setSelected(new Set((data.ideas ?? []).map((_, i) => i))); // 기본 전체 선택
    } catch (e) {
      setError(e instanceof Error ? e.message : "문제가 발생했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  function toggle(i: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => (prev.size === ideas.length ? new Set() : new Set(ideas.map((_, i) => i))));
  }

  function addSelected() {
    const picked = ideas.filter((_, i) => selected.has(i));
    if (picked.length === 0) {
      setError("대기열에 추가할 아이디어를 선택해 주세요.");
      return;
    }
    setError("");
    const before = loadQueue().length;
    const after = addIdeas(picked, usedSeed).length;
    const added = after - before;
    setQueueCount(after);
    setAddedMsg(
      added === picked.length
        ? `${added}개를 대기열에 추가했어요.`
        : `${added}개 추가(중복 ${picked.length - added}개는 건너뜀).`,
    );
  }

  const allChecked = ideas.length > 0 && selected.size === ideas.length;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {loading && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-white/60 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
            <p className="text-sm font-medium text-slate-600">아이디어를 발굴 중이에요…</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-3">
          <Link href="/" className="font-bold tracking-tight">
            Prompt<span className="text-indigo-600">Site</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/queue"
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50"
            >
              대기열{queueCount > 0 ? ` (${queueCount})` : ""}
            </Link>
            <Link
              href="/dashboard"
              className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-slate-700"
            >
              대시보드
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-8">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">아이디어 발굴</h1>
        <p className="mt-2 text-slate-600">
          업종·주제·타깃을 한 줄로 적으면, 랜딩페이지로 만들 만한 아이디어를 점수와 함께 찾아 드려요.
          마음에 드는 걸 대기열에 담아 한 번에 생성하세요.
        </p>

        {status?.mock && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            🧪 데모(목) 모드 — 키가 없어 시드와 느슨하게 연동된 샘플 아이디어가 나와요. 실제 발굴은
            AI 키 연결 후 동작합니다.
          </div>
        )}

        {/* 시드 입력 */}
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !loading) onDiscover();
              }}
              placeholder="예) 30대 직장인 대상 온라인 PT 코칭"
              maxLength={300}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-base outline-none focus:border-indigo-400"
            />
            <button
              onClick={onDiscover}
              disabled={loading}
              className="shrink-0 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? "발굴 중…" : "발굴 시작"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLE_SEEDS.map((ex) => (
              <button
                key={ex}
                onClick={() => setSeed(ex)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {addedMsg && (
          <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <span className="font-medium">{addedMsg}</span>
            <Link href="/queue" className="underline">
              대기열에서 생성하기 →
            </Link>
          </div>
        )}

        {/* 결과표 */}
        {ideas.length > 0 && (
          <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
              <span className="text-sm font-medium text-slate-500">
                “{usedSeed}” 결과 {ideas.length}개 · 적합도 높은 순
              </span>
              <button
                onClick={addSelected}
                disabled={selected.size === 0}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
              >
                선택 {selected.size}개 대기열에 추가
              </button>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="w-10 px-4 py-2">
                    <input
                      type="checkbox"
                      checked={allChecked}
                      onChange={toggleAll}
                      aria-label="전체 선택"
                      className="h-4 w-4 accent-indigo-600"
                    />
                  </th>
                  <th className="px-4 py-2">아이디어 (한 줄 프롬프트)</th>
                  <th className="w-24 px-4 py-2">적합도</th>
                  <th className="px-4 py-2">근거</th>
                </tr>
              </thead>
              <tbody>
                {ideas.map((idea, i) => (
                  <tr
                    key={i}
                    onClick={() => toggle(i)}
                    className="cursor-pointer border-t border-slate-100 transition hover:bg-slate-50"
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(i)}
                        onChange={() => toggle(i)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`선택: ${idea.idea}`}
                        className="h-4 w-4 accent-indigo-600"
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-800">{idea.idea}</td>
                    <td className="px-4 py-3">
                      <ScoreBadge score={idea.fitScore} />
                    </td>
                    <td className="px-4 py-3 text-slate-500">{idea.rationale || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {ideas.length === 0 && !loading && (
          <p className="mt-10 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-slate-500">
            시드를 적고 “발굴 시작”을 누르면 아이디어 후보가 여기에 표시돼요.
          </p>
        )}
      </main>
    </div>
  );
}

/** 적합도 점수 배지(점수대별 색). 실데이터가 아닌 LLM 추정값임에 유의. */
function ScoreBadge({ score }: { score: number }) {
  const tone =
    score >= 75
      ? "bg-emerald-100 text-emerald-700"
      : score >= 50
        ? "bg-amber-100 text-amber-700"
        : "bg-slate-100 text-slate-500";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>{score}</span>;
}
