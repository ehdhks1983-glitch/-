"use client";

// app/wordpress/write/page.tsx  [신규 — 워드프레스 자동 발행]
// AI 글쓰기: 주제 입력 → 초안 생성 → 수정 → 즉시/임시/예약 발행.
// 본문 미리보기는 sanitizeWpHtml(허용 태그만 속성 없이 재조립)을 거친 HTML만 렌더한다.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import NotConnected from "@/components/wp/NotConnected";
import { useWpConnection, wpApi } from "@/lib/wp/clientStore";
import { sanitizeWpHtml } from "@/lib/wp/sanitizeHtml";
import type { GeneratedPost, WpCategory } from "@/lib/wp/types";

type PublishMode = "publish" | "draft" | "future";

interface CreatedPostRes {
  post: { id: number; link: string; status: string; dateGmt: string; title: string };
}

const TONES = ["친절한 정보 전달형", "친근한 경험담형", "전문가 분석형"];
const LENGTHS = [
  { value: "short", label: "짧게 (600~900자)" },
  { value: "medium", label: "보통 (1,200~1,800자)" },
  { value: "long", label: "길게 (2,000~3,000자)" },
] as const;

/** 본문 미리보기 타이포그래피(허용 태그에 맞춘 최소 스타일) */
const PREVIEW_CLASS =
  "text-sm leading-7 text-slate-800 [&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-xl [&_h2]:font-bold " +
  "[&_h3]:mt-5 [&_h3]:mb-1.5 [&_h3]:text-lg [&_h3]:font-semibold [&_h4]:mt-4 [&_h4]:font-semibold " +
  "[&_p]:my-3 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5 " +
  "[&_li]:my-1 [&_blockquote]:my-3 [&_blockquote]:border-l-4 [&_blockquote]:border-indigo-200 " +
  "[&_blockquote]:pl-3 [&_blockquote]:text-slate-600";

function defaultScheduleValue(): string {
  // 내일 오전 9시(로컬) — datetime-local 형식
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function WpWritePage() {
  const conn = useWpConnection();

  // 생성 옵션
  const [topic, setTopic] = useState("");
  const [categoryId, setCategoryId] = useState(0);
  const [tone, setTone] = useState(TONES[0]);
  const [length, setLength] = useState<(typeof LENGTHS)[number]["value"]>("medium");
  const [extra, setExtra] = useState("");

  // 초안
  const [draft, setDraft] = useState<GeneratedPost | null>(null);
  const [tagsText, setTagsText] = useState("");
  const [showHtml, setShowHtml] = useState(false);

  // 발행 옵션
  const [publishMode, setPublishMode] = useState<PublishMode>("publish");
  const [scheduleAt, setScheduleAt] = useState(defaultScheduleValue());

  const [cats, setCats] = useState<WpCategory[]>([]);
  const [generating, setGenerating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<CreatedPostRes["post"] | null>(null);
  const [mock, setMock] = useState(false);

  useEffect(() => {
    if (!conn) return;
    wpApi<{ categories: WpCategory[] }>("/api/wp/categories")
      .then(({ categories }) => setCats(categories))
      .catch(() => setCats([]));
    fetch("/api/status")
      .then((r) => r.json())
      .then((s: { mock?: boolean }) => setMock(s.mock === true))
      .catch(() => {});
  }, [conn]);

  const previewHtml = useMemo(
    () => (draft ? sanitizeWpHtml(draft.html) : ""),
    [draft],
  );

  if (conn === undefined) {
    return <p className="py-20 text-center text-sm text-slate-400">불러오는 중…</p>;
  }
  if (!conn) return <NotConnected />;

  async function generate() {
    setError("");
    setDone(null);
    setGenerating(true);
    try {
      const categoryName = cats.find((c) => c.id === categoryId)?.name;
      const { post } = await wpApi<{ post: GeneratedPost }>("/api/wp/generate", {
        json: { topic, categoryName, tone, length, extra },
      });
      setDraft(post);
      setTagsText(post.tags.join(", "));
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성에 실패했어요.");
    } finally {
      setGenerating(false);
    }
  }

  async function publish() {
    if (!draft) return;
    setError("");
    setPublishing(true);
    try {
      const tags = tagsText.split(",").map((t) => t.trim()).filter(Boolean);
      const payload: Record<string, unknown> = {
        title: draft.title,
        html: draft.html,
        excerpt: draft.excerpt,
        tags,
        status: publishMode,
      };
      if (categoryId) payload.categoryId = categoryId;
      if (publishMode === "future") {
        const when = new Date(scheduleAt);
        if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
          throw new Error("예약 시각을 미래로 선택해 주세요.");
        }
        payload.dateGmt = when.toISOString();
      }
      const { post } = await wpApi<CreatedPostRes>("/api/wp/posts", { json: payload });
      setDone(post);
    } catch (e) {
      setError(e instanceof Error ? e.message : "발행에 실패했어요.");
    } finally {
      setPublishing(false);
    }
  }

  function resetAll() {
    setDraft(null);
    setDone(null);
    setTopic("");
    setExtra("");
    setError("");
  }

  // ── 발행 완료 화면 ──
  if (done) {
    const statusLabel =
      done.status === "publish" ? "발행 완료" : done.status === "future" ? "예약 완료" : "임시 저장 완료";
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-emerald-200 bg-white p-10 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-2xl">
          ✅
        </div>
        <h1 className="text-xl font-bold">{statusLabel}</h1>
        <p className="mt-2 break-keep text-sm text-slate-600">“{done.title}”</p>
        {done.link && done.status === "publish" && (
          <a
            href={done.link}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block break-all text-sm text-indigo-600 underline"
          >
            {done.link}
          </a>
        )}
        <div className="mt-8 flex justify-center gap-2">
          <button
            onClick={resetAll}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
          >
            새 글 쓰기
          </button>
          <Link
            href="/wordpress/posts"
            className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            발행 현황 보기
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold">AI 글쓰기</h1>
      <p className="mt-1 text-sm text-slate-500">
        주제만 정하면 초안을 만들어 드려요. 검토·수정 후 {conn.siteName}에 바로 올립니다.
      </p>

      {mock && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          지금은 AI 키가 없는 <b>데모 모드</b>라 예시 초안이 생성됩니다. 실제 글 생성은 서버에
          ANTHROPIC_API_KEY 등 프로바이더 키를 설정해 주세요.
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        {/* ── 좌: 생성 옵션 ── */}
        <section className="h-fit rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-2">
          <div className="space-y-4">
            <div>
              <label htmlFor="w-topic" className="text-sm font-medium text-slate-700">
                주제 / 핵심 키워드 <span className="text-red-500">*</span>
              </label>
              <input
                id="w-topic"
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                maxLength={100}
                placeholder="예: 소상공인 정부지원금 신청 방법"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="w-cat" className="text-sm font-medium text-slate-700">
                카테고리
              </label>
              <select
                id="w-cat"
                value={categoryId}
                onChange={(e) => setCategoryId(Number(e.target.value))}
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              >
                <option value={0}>선택 안 함 (기본 카테고리)</option>
                {cats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.count})
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="w-tone" className="text-sm font-medium text-slate-700">
                  말투
                </label>
                <select
                  id="w-tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
                >
                  {TONES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="w-len" className="text-sm font-medium text-slate-700">
                  분량
                </label>
                <select
                  id="w-len"
                  value={length}
                  onChange={(e) => setLength(e.target.value as typeof length)}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
                >
                  {LENGTHS.map((l) => (
                    <option key={l.value} value={l.value}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="w-extra" className="text-sm font-medium text-slate-700">
                추가 요청사항 (선택)
              </label>
              <textarea
                id="w-extra"
                value={extra}
                onChange={(e) => setExtra(e.target.value)}
                maxLength={500}
                rows={3}
                placeholder="예: 신청 서류 체크리스트를 꼭 넣어줘"
                className="mt-1.5 w-full resize-y rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <button
              onClick={generate}
              disabled={generating || topic.trim().length < 2}
              className="w-full rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? "초안 작성 중… (최대 1분)" : draft ? "다시 생성" : "AI 초안 생성"}
            </button>
          </div>
        </section>

        {/* ── 우: 초안 + 발행 ── */}
        <section className="rounded-2xl border border-slate-200 bg-white lg:col-span-3">
          {!draft ? (
            <p className="px-6 py-24 text-center text-sm text-slate-400">
              왼쪽에서 주제를 입력하고 [AI 초안 생성]을 누르면
              <br />
              여기에서 확인·수정 후 발행할 수 있어요.
            </p>
          ) : (
            <div className="divide-y divide-slate-100">
              <div className="px-6 py-4">
                <label htmlFor="w-title" className="text-xs font-medium text-slate-400">
                  제목
                </label>
                <input
                  id="w-title"
                  type="text"
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  maxLength={200}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base font-semibold focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="px-6 py-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">본문</span>
                  <button
                    onClick={() => setShowHtml((v) => !v)}
                    className="text-xs font-medium text-indigo-600 hover:underline"
                  >
                    {showHtml ? "미리보기로" : "HTML 직접 편집"}
                  </button>
                </div>
                {showHtml ? (
                  <textarea
                    value={draft.html}
                    onChange={(e) => setDraft({ ...draft, html: e.target.value })}
                    rows={14}
                    className="mt-2 w-full resize-y rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs leading-5 focus:border-indigo-500 focus:outline-none"
                  />
                ) : (
                  <div
                    className={`mt-2 max-h-[420px] overflow-y-auto rounded-lg border border-slate-100 bg-slate-50/50 px-4 py-1 ${PREVIEW_CLASS}`}
                    // 허용 태그만 속성 없이 재조립(sanitizeWpHtml)한 HTML — XSS 벡터 없음
                    dangerouslySetInnerHTML={{ __html: previewHtml }}
                  />
                )}
              </div>

              <div className="grid gap-4 px-6 py-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="w-excerpt" className="text-xs font-medium text-slate-400">
                    요약 (검색 결과·목록 노출)
                  </label>
                  <textarea
                    id="w-excerpt"
                    value={draft.excerpt}
                    onChange={(e) => setDraft({ ...draft, excerpt: e.target.value })}
                    maxLength={300}
                    rows={3}
                    className="mt-1 w-full resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label htmlFor="w-tags" className="text-xs font-medium text-slate-400">
                    태그 (쉼표로 구분)
                  </label>
                  <textarea
                    id="w-tags"
                    value={tagsText}
                    onChange={(e) => setTagsText(e.target.value)}
                    rows={3}
                    placeholder="키워드1, 키워드2"
                    className="mt-1 w-full resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="px-6 py-4">
                <span className="text-xs font-medium text-slate-400">발행 방법</span>
                <div className="mt-2 flex flex-wrap items-center gap-4">
                  {(
                    [
                      ["publish", "지금 발행"],
                      ["draft", "임시글로 저장"],
                      ["future", "예약 발행"],
                    ] as [PublishMode, string][]
                  ).map(([value, label]) => (
                    <label key={value} className="flex items-center gap-1.5 text-sm text-slate-700">
                      <input
                        type="radio"
                        name="publishMode"
                        checked={publishMode === value}
                        onChange={() => setPublishMode(value)}
                        className="accent-indigo-600"
                      />
                      {label}
                    </label>
                  ))}
                  {publishMode === "future" && (
                    <input
                      type="datetime-local"
                      value={scheduleAt}
                      onChange={(e) => setScheduleAt(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                    />
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between gap-3 px-6 py-4">
                <p className="min-h-5 text-sm text-red-600">{error}</p>
                <button
                  onClick={publish}
                  disabled={publishing || !draft.title.trim()}
                  className="shrink-0 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                >
                  {publishing
                    ? "등록 중…"
                    : publishMode === "publish"
                      ? "워드프레스에 발행"
                      : publishMode === "draft"
                        ? "임시글로 저장"
                        : "예약 등록"}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      {!draft && error && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}
