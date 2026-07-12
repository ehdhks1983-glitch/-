"use client";

// app/wordpress/posts/page.tsx  [신규 — 워드프레스 자동 발행]
// 발행 현황: 발행·예약·임시글을 필터로 보고, 예약/임시글은 즉시 발행하거나 삭제한다.

import { useCallback, useEffect, useMemo, useState } from "react";
import NotConnected from "@/components/wp/NotConnected";
import { useWpConnection, wpApi, formatWpDate } from "@/lib/wp/clientStore";
import type { WpCategory, WpPostSummary } from "@/lib/wp/types";

const FILTERS = [
  { key: "all", label: "전체", statuses: "all" },
  { key: "publish", label: "발행됨", statuses: "publish" },
  { key: "future", label: "예약됨", statuses: "future" },
  { key: "draft", label: "임시글", statuses: "draft,pending" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  publish: { label: "발행됨", cls: "bg-emerald-50 text-emerald-700" },
  future: { label: "예약됨", cls: "bg-indigo-50 text-indigo-700" },
  draft: { label: "임시글", cls: "bg-amber-50 text-amber-700" },
  pending: { label: "검토 대기", cls: "bg-amber-50 text-amber-700" },
  private: { label: "비공개", cls: "bg-slate-100 text-slate-600" },
};

interface ListRes {
  posts: WpPostSummary[];
  total: number;
  totalPages: number;
}

export default function WpPostsPage() {
  const conn = useWpConnection();

  const [filter, setFilter] = useState<FilterKey>("all");
  const [page, setPage] = useState(1);
  const [posts, setPosts] = useState<WpPostSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [cats, setCats] = useState<WpCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const catName = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of cats) m.set(c.id, c.name);
    return m;
  }, [cats]);

  // effect에서 호출되므로 setState는 전부 프로미스 콜백(비동기) 안에서만 한다.
  // 스피너가 필요한 재조회는 호출부(이벤트 핸들러)에서 setLoading(true)를 먼저 켠다.
  const load = useCallback(() => {
    const statuses = FILTERS.find((f) => f.key === filter)?.statuses ?? "all";
    return wpApi<ListRes>(`/api/wp/posts?status=${statuses}&page=${page}`)
      .then((data) => {
        setPosts(data.posts);
        setTotal(data.total);
        setTotalPages(data.totalPages);
        setError("");
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "목록을 불러오지 못했어요.");
        setPosts([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [filter, page]);

  useEffect(() => {
    if (conn) void load();
  }, [conn, load]);

  useEffect(() => {
    if (!conn) return;
    wpApi<{ categories: WpCategory[] }>("/api/wp/categories")
      .then(({ categories }) => setCats(categories))
      .catch(() => setCats([]));
  }, [conn]);

  if (conn === undefined) {
    return <p className="py-20 text-center text-sm text-slate-400">불러오는 중…</p>;
  }
  if (!conn) return <NotConnected />;

  async function publishNow(post: WpPostSummary) {
    if (!window.confirm(`"${post.title}" 글을 지금 바로 발행할까요?`)) return;
    setBusyId(post.id);
    try {
      await wpApi(`/api/wp/posts/${post.id}`, { method: "PATCH", json: { publishNow: true } });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "발행에 실패했어요.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(post: WpPostSummary) {
    if (!window.confirm(`"${post.title}" 글을 삭제할까요? (워드프레스 휴지통으로 이동)`)) return;
    setBusyId(post.id);
    try {
      await wpApi(`/api/wp/posts/${post.id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제에 실패했어요.");
    } finally {
      setBusyId(null);
    }
  }

  function changeFilter(key: FilterKey) {
    setLoading(true);
    setFilter(key);
    setPage(1);
  }

  function changePage(next: number) {
    setLoading(true);
    setPage(next);
  }

  const editUrl = (id: number) => `${conn.url}/wp-admin/post.php?post=${id}&action=edit`;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">발행 현황</h1>
          <p className="mt-1 text-sm text-slate-500">
            {conn.siteName} · 총 {total}개
          </p>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            void load();
          }}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
        >
          새로고침
        </button>
      </div>

      <div className="mt-4 flex gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => changeFilter(f.key)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              filter === f.key
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</p>
      )}

      <section className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        {loading ? (
          <p className="px-6 py-16 text-center text-sm text-slate-400">불러오는 중…</p>
        ) : posts.length === 0 ? (
          <p className="px-6 py-16 text-center text-sm text-slate-400">
            해당하는 글이 없어요. [AI 글쓰기]나 [대량 자동화]로 첫 글을 만들어 보세요.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {posts.map((p) => {
              const badge = STATUS_BADGE[p.status] ?? {
                label: p.status,
                cls: "bg-slate-100 text-slate-600",
              };
              const canPublishNow = p.status === "future" || p.status === "draft" || p.status === "pending";
              const busy = busyId === p.id;
              return (
                <li key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                  <span
                    className={`inline-flex w-20 shrink-0 justify-center rounded-full px-2 py-0.5 text-xs font-semibold ${badge.cls}`}
                  >
                    {badge.label}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">
                      {p.status === "publish" && p.link ? (
                        <a href={p.link} target="_blank" rel="noreferrer" className="hover:text-indigo-700 hover:underline">
                          {p.title}
                        </a>
                      ) : (
                        p.title
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {p.status === "future" ? "예약: " : ""}
                      {formatWpDate(p.dateGmt)}
                      {p.categories.length > 0 && (
                        <>
                          {" · "}
                          {p.categories.map((id) => catName.get(id) ?? `#${id}`).join(", ")}
                        </>
                      )}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {canPublishNow && (
                      <button
                        onClick={() => void publishNow(p)}
                        disabled={busy}
                        className="rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-100 disabled:opacity-50"
                      >
                        지금 발행
                      </button>
                    )}
                    <a
                      href={editUrl(p.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
                    >
                      WP에서 편집
                    </a>
                    <button
                      onClick={() => void remove(p)}
                      disabled={busy}
                      className="rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-50"
                    >
                      삭제
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm">
          <button
            onClick={() => changePage(Math.max(1, page - 1))}
            disabled={page <= 1 || loading}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-40"
          >
            ← 이전
          </button>
          <span className="text-slate-500">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => changePage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages || loading}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-40"
          >
            다음 →
          </button>
        </div>
      )}
    </div>
  );
}
