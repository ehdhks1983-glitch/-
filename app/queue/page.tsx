"use client";

// app/queue/page.tsx  [신규]
// 대기열 소비 화면 — 블로그봇 "발행 탭이 대기열을 소비"의 등가물.
// 큐의 status="대기" 항목을 하나씩 꺼내 → idea(한 줄 프롬프트)를 기존 생성 파이프라인에 그대로 투입:
//   1) POST /api/generate { prompt: idea, skipClarify: true }  → biz/template/copy
//   2) POST /api/projects { prompt, title, template, biz_info, copy } → { id, slug } (게시)
// 직전 status="생성중", 성공 "완료"(+slug/projectId/generatedAt), 실패 "실패"(+error)로 역기록.
// ※ 기존 /api/generate·/api/projects 는 수정하지 않고 그대로 재사용한다(회귀 안전).

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  loadQueue,
  updateItem,
  removeItem,
  clearFinished,
  countByStatus,
  type QueueItem,
} from "@/lib/queue/queue";

interface AppStatus {
  mock: boolean;
  supabaseConfigured: boolean;
}

export default function QueuePage() {
  const router = useRouter();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [runningId, setRunningId] = useState("");
  const [batch, setBatch] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<AppStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await Promise.resolve(); // effect 본문 동기 setState 회피(set-state-in-effect 규칙)
      if (cancelled) return;
      setItems(loadQueue());
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

  function refresh() {
    setItems(loadQueue());
  }

  /** 한 건 생성: 기존 파이프라인 재사용. @returns 성공 여부(배치 중단 판단용). */
  async function generateOne(item: QueueItem): Promise<boolean> {
    setRunningId(item.id);
    updateItem(item.id, { status: "생성중", error: "" });
    refresh();
    try {
      // 1) 원고(카피) 생성 — 보완질문은 건너뛰고 바로 생성(배치/무인)
      const gen = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: item.idea, skipClarify: true }),
      });
      const gdata = (await gen.json().catch(() => ({}))) as {
        stage?: string;
        biz?: { service_name?: string };
        template?: string;
        copy?: unknown;
        error?: string;
      };
      if (gen.status === 401) {
        // 미인증: 상태를 대기로 되돌리고 로그인으로
        updateItem(item.id, { status: "대기" });
        router.push("/login");
        return false;
      }
      if (!gen.ok) throw new Error(gdata?.error || "생성에 실패했어요.");
      if (gdata.stage !== "done" || !gdata.copy) throw new Error("생성 결과가 비어 있어요.");

      // 2) 게시(저장) — 기존 수동 게시와 동일한 페이로드
      const save = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: item.idea,
          title: gdata.biz?.service_name ?? "",
          template: gdata.template,
          biz_info: gdata.biz,
          copy: gdata.copy,
        }),
      });
      const sdata = (await save.json().catch(() => ({}))) as { id?: string; slug?: string; error?: string };
      if (save.status === 401) {
        updateItem(item.id, { status: "대기" });
        router.push("/login");
        return false;
      }
      if (!save.ok) throw new Error(sdata?.error || "게시에 실패했어요.");

      updateItem(item.id, {
        status: "완료",
        slug: sdata.slug ?? "",
        projectId: sdata.id ?? "",
        generatedAt: new Date().toISOString(),
        error: "",
      });
      refresh();
      return true;
    } catch (e) {
      updateItem(item.id, {
        status: "실패",
        error: e instanceof Error ? e.message : "문제가 발생했어요.",
      });
      refresh();
      return false;
    } finally {
      setRunningId("");
    }
  }

  async function generateAll() {
    setError("");
    setBatch(true);
    try {
      // 매 반복마다 최신 큐에서 대기 항목을 다시 읽어 안전하게 순차 처리
      let guard = 0;
      while (guard < 100) {
        guard += 1;
        const next = loadQueue().find((i) => i.status === "대기");
        if (!next) break;
        const ok = await generateOne(next);
        if (!ok && loadQueue().find((i) => i.id === next.id)?.status === "대기") break; // 로그인 이동 등으로 중단
      }
    } finally {
      setBatch(false);
    }
  }

  function onRemove(id: string) {
    setItems(removeItem(id));
  }

  function onClearFinished() {
    setItems(clearFinished());
  }

  const counts = countByStatus(items);
  const pendingCount = counts["대기"];
  const busy = batch || runningId !== "";
  const gateOff = status !== null && !status.supabaseConfigured;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-3">
          <Link href="/" className="font-bold tracking-tight">
            Prompt<span className="text-indigo-600">Site</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/discover"
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50"
            >
              + 아이디어 발굴
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
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">발행 대기열</h1>
            <p className="mt-2 text-slate-600">
              대기 중인 아이디어를 기존 생성 파이프라인으로 한 번에 만들어 게시합니다.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={generateAll}
              disabled={busy || pendingCount === 0 || gateOff}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {batch ? "생성 중…" : `전체 생성 (${pendingCount})`}
            </button>
            <button
              onClick={onClearFinished}
              disabled={busy || counts["완료"] + counts["실패"] === 0}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium transition hover:bg-white disabled:opacity-50"
            >
              완료·실패 정리
            </button>
          </div>
        </div>

        {/* 상태 요약 */}
        {items.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <Pill label="대기" n={counts["대기"]} tone="bg-slate-100 text-slate-600" />
            <Pill label="생성중" n={counts["생성중"]} tone="bg-indigo-100 text-indigo-700" />
            <Pill label="완료" n={counts["완료"]} tone="bg-emerald-100 text-emerald-700" />
            <Pill label="실패" n={counts["실패"]} tone="bg-red-100 text-red-700" />
          </div>
        )}

        {gateOff && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            생성·게시는 로그인과 Supabase 설정이 필요해요. 설정 후 다시 시도해 주세요. (발굴·대기열 담기는 그대로 동작)
          </div>
        )}
        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* 목록 */}
        {items.length === 0 ? (
          <div className="mt-10 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-slate-500">
            <p>대기열이 비어 있어요.</p>
            <Link
              href="/discover"
              className="mt-4 inline-block rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white"
            >
              아이디어 발굴하러 가기
            </Link>
          </div>
        ) : (
          <ul className="mt-6 space-y-3">
            {items.map((it) => (
              <li key={it.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={it.status} />
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
                        적합도 {it.fitScore}
                      </span>
                    </div>
                    <p className="mt-2 font-medium text-slate-800">{it.idea}</p>
                    {it.rationale && <p className="mt-1 text-sm text-slate-500">{it.rationale}</p>}
                    {it.status === "실패" && it.error && (
                      <p className="mt-1 text-sm text-red-600">실패: {it.error}</p>
                    )}
                    {it.status === "완료" && it.slug && (
                      <div className="mt-2 flex flex-wrap gap-3 text-sm">
                        <a
                          href={`/s/${it.slug}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-indigo-600 underline"
                        >
                          공개 페이지 →
                        </a>
                        {it.projectId && (
                          <Link href={`/project/${it.projectId}`} className="text-slate-500 underline">
                            편집
                          </Link>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {(it.status === "대기" || it.status === "실패") && (
                      <button
                        onClick={() => generateOne(it)}
                        disabled={busy || gateOff}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                      >
                        {runningId === it.id ? "생성 중…" : it.status === "실패" ? "다시 시도" : "생성"}
                      </button>
                    )}
                    <button
                      onClick={() => onRemove(it.id)}
                      disabled={runningId === it.id}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
                    >
                      삭제
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}

function Pill({ label, n, tone }: { label: string; n: number; tone: string }) {
  return <span className={`rounded-full px-2.5 py-1 font-medium ${tone}`}>{label} {n}</span>;
}

function StatusBadge({ status }: { status: QueueItem["status"] }) {
  const tone =
    status === "완료"
      ? "bg-emerald-100 text-emerald-700"
      : status === "실패"
        ? "bg-red-100 text-red-700"
        : status === "생성중"
          ? "bg-indigo-100 text-indigo-700"
          : "bg-slate-100 text-slate-600";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>{status}</span>;
}
