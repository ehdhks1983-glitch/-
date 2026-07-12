"use client";

// app/wordpress/categories/page.tsx  [신규 — 워드프레스 자동 발행]
// 카테고리 관리 — 블로그 관리자에 익숙한 2패널 구성(좌: 전체보기 트리, 우: 설정).
// 좌측에서 고르면 우측에서 이름/주소/설명/상위 카테고리를 수정한다.

import { useCallback, useEffect, useMemo, useState } from "react";
import NotConnected from "@/components/wp/NotConnected";
import { useWpConnection, wpApi } from "@/lib/wp/clientStore";
import type { WpCategory } from "@/lib/wp/types";

type Mode = "edit" | "create";

interface CatNode extends WpCategory {
  depth: number;
}

/** parent 관계로 트리 순서(부모 아래 자식, 깊이 표시)를 만든다 */
function flattenTree(cats: WpCategory[]): CatNode[] {
  const byParent = new Map<number, WpCategory[]>();
  for (const c of cats) {
    const list = byParent.get(c.parent) ?? [];
    list.push(c);
    byParent.set(c.parent, list);
  }
  const out: CatNode[] = [];
  const walk = (parent: number, depth: number) => {
    for (const c of byParent.get(parent) ?? []) {
      out.push({ ...c, depth });
      if (depth < 4) walk(c.id, depth + 1);
    }
  };
  walk(0, 0);
  // 고아 노드(부모가 목록에 없음) 안전 처리
  const seen = new Set(out.map((c) => c.id));
  for (const c of cats) if (!seen.has(c.id)) out.push({ ...c, depth: 0 });
  return out;
}

/** id 기준 자기 자신 + 모든 하위 id (상위 카테고리 선택에서 제외해 순환 방지) */
function descendantIds(cats: WpCategory[], rootId: number): Set<number> {
  const ids = new Set<number>([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of cats) {
      if (ids.has(c.parent) && !ids.has(c.id)) {
        ids.add(c.id);
        grew = true;
      }
    }
  }
  return ids;
}

export default function WpCategoriesPage() {
  const conn = useWpConnection();

  const [cats, setCats] = useState<WpCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [mode, setMode] = useState<Mode>("edit");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [parent, setParent] = useState(0);
  const [saving, setSaving] = useState(false);

  const tree = useMemo(() => flattenTree(cats), [cats]);
  const totalCount = useMemo(() => cats.reduce((sum, c) => sum + c.count, 0), [cats]);
  const selected = cats.find((c) => c.id === selectedId) ?? null;
  const blockedParents = useMemo(
    () => (mode === "edit" && selectedId ? descendantIds(cats, selectedId) : new Set<number>()),
    [cats, mode, selectedId],
  );

  // effect에서 호출되므로 setState는 전부 프로미스 콜백(비동기) 안에서만 한다.
  // 스피너가 필요한 재조회는 호출부(이벤트 핸들러)에서 setLoading(true)를 먼저 켠다.
  const load = useCallback(() => {
    return wpApi<{ categories: WpCategory[] }>("/api/wp/categories")
      .then(({ categories }) => {
        setCats(categories);
        setError("");
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "카테고리를 불러오지 못했어요.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (conn) void load();
  }, [conn, load]);

  function select(cat: WpCategory) {
    setMode("edit");
    setSelectedId(cat.id);
    setName(cat.name);
    setSlug(cat.slug);
    setDescription(cat.description);
    setParent(cat.parent);
    setNotice("");
  }

  function startCreate() {
    setMode("create");
    setSelectedId(null);
    setName("");
    setSlug("");
    setDescription("");
    setParent(0);
    setNotice("");
  }

  async function save() {
    if (!name.trim()) {
      setNotice("카테고리명을 입력해 주세요.");
      return;
    }
    setSaving(true);
    setNotice("");
    try {
      if (mode === "create") {
        const { category } = await wpApi<{ category: WpCategory }>("/api/wp/categories", {
          json: { name: name.trim(), slug: slug.trim(), description: description.trim(), parent },
        });
        await load();
        select(category);
        setNotice("카테고리를 추가했어요.");
      } else if (selectedId) {
        await wpApi(`/api/wp/categories/${selectedId}`, {
          method: "PATCH",
          json: { name: name.trim(), slug: slug.trim(), description: description.trim(), parent },
        });
        await load();
        setNotice("저장했어요.");
      }
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "저장에 실패했어요.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!selected) return;
    const ok = window.confirm(
      `"${selected.name}" 카테고리를 삭제할까요?\n소속 글 ${selected.count}개는 워드프레스 기본 카테고리로 이동합니다.`,
    );
    if (!ok) return;
    setSaving(true);
    setNotice("");
    try {
      await wpApi(`/api/wp/categories/${selected.id}`, { method: "DELETE" });
      setSelectedId(null);
      setName("");
      setSlug("");
      setDescription("");
      setParent(0);
      await load();
      setNotice("삭제했어요.");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "삭제에 실패했어요.");
    } finally {
      setSaving(false);
    }
  }

  if (conn === undefined) {
    return <p className="py-20 text-center text-sm text-slate-400">불러오는 중…</p>;
  }
  if (!conn) return <NotConnected />;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">카테고리 관리 · 설정</h1>
          <p className="mt-1 text-sm text-slate-500">{conn.siteName}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={startCreate}
            className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-semibold text-indigo-700 transition hover:bg-indigo-100"
          >
            + 카테고리 추가
          </button>
          <button
            onClick={remove}
            disabled={!selected || saving}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            − 삭제
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 flex items-center justify-between rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
          <span>{error}</span>
          <button
            onClick={() => {
              setLoading(true);
              void load();
            }}
            className="font-semibold underline"
          >
            다시 시도
          </button>
        </div>
      )}

      <div className="mt-5 grid gap-6 lg:grid-cols-5">
        {/* ── 좌: 카테고리 전체보기 ── */}
        <section className="rounded-2xl border border-slate-200 bg-white lg:col-span-2">
          <header className="border-b border-slate-200 px-4 py-3">
            <span className="font-semibold">
              카테고리 전체보기{" "}
              <span className="text-slate-400">({loading ? "…" : totalCount})</span>
            </span>
          </header>
          <div className="max-h-[480px] overflow-y-auto p-2">
            {loading ? (
              <p className="px-3 py-8 text-center text-sm text-slate-400">불러오는 중…</p>
            ) : tree.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-slate-400">
                카테고리가 없어요. [+ 카테고리 추가]로 시작하세요.
              </p>
            ) : (
              <ul className="space-y-0.5">
                {tree.map((c) => (
                  <li key={c.id}>
                    <button
                      onClick={() => select(c)}
                      className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
                        selectedId === c.id
                          ? "bg-indigo-50 font-semibold text-indigo-700"
                          : "text-slate-700 hover:bg-slate-50"
                      }`}
                      style={{ paddingLeft: `${12 + c.depth * 16}px` }}
                    >
                      <span className="truncate">
                        {c.depth > 0 && <span className="mr-1 text-slate-300">└</span>}
                        {c.name}
                        <span className="ml-1 text-xs font-normal text-slate-400">({c.count})</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* ── 우: 설정 폼 ── */}
        <section className="rounded-2xl border border-slate-200 bg-white lg:col-span-3">
          <header className="border-b border-slate-200 px-6 py-3">
            <span className="font-semibold">
              {mode === "create" ? "새 카테고리" : selected ? `설정 — ${selected.name}` : "설정"}
            </span>
          </header>

          {mode === "edit" && !selected ? (
            <p className="px-6 py-16 text-center text-sm text-slate-400">
              왼쪽 목록에서 카테고리를 선택하거나 [+ 카테고리 추가]를 눌러 주세요.
            </p>
          ) : (
            <div className="divide-y divide-slate-100">
              <div className="grid gap-2 px-6 py-4 sm:grid-cols-[110px_1fr] sm:items-center">
                <label htmlFor="cat-name" className="text-sm font-medium text-slate-700">
                  카테고리명
                </label>
                <input
                  id="cat-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={100}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="grid gap-2 px-6 py-4 sm:grid-cols-[110px_1fr] sm:items-center">
                <label htmlFor="cat-slug" className="text-sm font-medium text-slate-700">
                  주소(슬러그)
                </label>
                <div>
                  <input
                    id="cat-slug"
                    type="text"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    maxLength={100}
                    placeholder="비우면 이름으로 자동 생성"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-slate-400">
                    카테고리 글 목록 주소에 쓰여요. 예: /category/<b>marketing</b>
                  </p>
                </div>
              </div>

              <div className="grid gap-2 px-6 py-4 sm:grid-cols-[110px_1fr] sm:items-center">
                <label htmlFor="cat-parent" className="text-sm font-medium text-slate-700">
                  상위 카테고리
                </label>
                <select
                  id="cat-parent"
                  value={parent}
                  onChange={(e) => setParent(Number(e.target.value))}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                >
                  <option value={0}>없음 (최상위)</option>
                  {tree
                    .filter((c) => !blockedParents.has(c.id))
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {" ".repeat(c.depth * 2)}
                        {c.name}
                      </option>
                    ))}
                </select>
              </div>

              <div className="grid gap-2 px-6 py-4 sm:grid-cols-[110px_1fr] sm:items-start">
                <label htmlFor="cat-desc" className="pt-2 text-sm font-medium text-slate-700">
                  설명
                </label>
                <textarea
                  id="cat-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  rows={3}
                  placeholder="테마에 따라 카테고리 페이지에 노출돼요. (선택)"
                  className="w-full resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-between gap-3 px-6 py-4">
                <p
                  className={`min-h-5 text-sm ${
                    notice.includes("했어요") ? "text-emerald-600" : "text-red-600"
                  }`}
                >
                  {notice}
                </p>
                <button
                  onClick={save}
                  disabled={saving}
                  className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                >
                  {saving ? "저장 중…" : mode === "create" ? "추가" : "저장"}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      <div className="mt-4 space-y-1 text-xs leading-5 text-slate-400">
        <p>· 카테고리를 삭제하면 소속 글은 워드프레스 기본 카테고리로 이동합니다(글은 지워지지 않아요).</p>
        <p>· 기본 카테고리(예: 미분류)는 워드프레스 정책상 삭제할 수 없습니다.</p>
        <p>· 글 개수는 발행된 글 기준이라 예약·임시글은 포함되지 않을 수 있어요.</p>
      </div>
    </div>
  );
}
