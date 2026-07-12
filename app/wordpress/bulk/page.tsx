"use client";

// app/wordpress/bulk/page.tsx  [신규 — 워드프레스 자동 발행]
// 대량 자동화: 키워드 여러 개 → 키워드마다 AI 글 생성 → 정한 간격으로 예약 발행(또는 임시글).
// 브라우저가 순차 실행하며 진행 상황을 보여준다. 예약 자체는 워드프레스가 처리하므로
// 등록이 끝난 뒤에는 이 탭을 닫아도 예약대로 발행된다.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import NotConnected from "@/components/wp/NotConnected";
import { useWpConnection, wpApi, WpApiClientError, formatWpDate } from "@/lib/wp/clientStore";
import type { GeneratedPost, WpCategory } from "@/lib/wp/types";

type ItemState = "wait" | "generating" | "posting" | "done" | "fail" | "skipped";

interface BulkItem {
  keyword: string;
  state: ItemState;
  scheduledFor?: string; // 로컬 표시용
  link?: string;
  error?: string;
}

const MAX_KEYWORDS = 20;
/** 429(속도 제한) 재시도 대기(ms)와 횟수 */
const RETRY_WAIT_MS = 15_000;
const MAX_RETRIES = 4;

const TONES = ["친절한 정보 전달형", "친근한 경험담형", "전문가 분석형"];
const LENGTHS = [
  { value: "short", label: "짧게" },
  { value: "medium", label: "보통" },
  { value: "long", label: "길게" },
] as const;
const INTERVALS = [
  { value: 1, label: "매일 (1일 간격)" },
  { value: 2, label: "2일 간격" },
  { value: 3, label: "3일 간격" },
  { value: 7, label: "매주 (7일 간격)" },
];

const STATE_LABEL: Record<ItemState, string> = {
  wait: "대기",
  generating: "글 생성 중…",
  posting: "등록 중…",
  done: "완료",
  fail: "실패",
  skipped: "중단됨",
};

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function tomorrowDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 429 는 잠시 기다렸다 재시도하는 호출 래퍼 */
async function callWithRetry<T>(fn: () => Promise<T>, cancelled: () => boolean): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fn();
    } catch (e) {
      const canRetry =
        e instanceof WpApiClientError && e.status === 429 && attempt < MAX_RETRIES && !cancelled();
      if (!canRetry) throw e;
      await sleep(RETRY_WAIT_MS);
    }
  }
}

export default function WpBulkPage() {
  const conn = useWpConnection();

  const [keywordsText, setKeywordsText] = useState("");
  const [categoryId, setCategoryId] = useState(0);
  const [tone, setTone] = useState(TONES[0]);
  const [length, setLength] = useState<(typeof LENGTHS)[number]["value"]>("medium");
  const [registerMode, setRegisterMode] = useState<"future" | "draft">("future");
  const [startDate, setStartDate] = useState(tomorrowDate());
  const [time, setTime] = useState("09:00");
  const [intervalDays, setIntervalDays] = useState(1);

  const [cats, setCats] = useState<WpCategory[]>([]);
  const [items, setItems] = useState<BulkItem[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState("");
  const cancelRef = useRef(false);

  useEffect(() => {
    if (!conn) return;
    wpApi<{ categories: WpCategory[] }>("/api/wp/categories")
      .then(({ categories }) => setCats(categories))
      .catch(() => setCats([]));
  }, [conn]);

  // 실행 중 이탈 방지(예약 등록이 끊기면 일부만 등록됨)
  useEffect(() => {
    if (!running) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [running]);

  if (conn === undefined) {
    return <p className="py-20 text-center text-sm text-slate-400">불러오는 중…</p>;
  }
  if (!conn) return <NotConnected />;

  const keywords = [...new Set(keywordsText.split("\n").map((k) => k.trim()).filter(Boolean))];

  function updateItem(index: number, patch: Partial<BulkItem>) {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  }

  async function run() {
    setError("");
    setSummary("");

    if (keywords.length === 0) {
      setError("키워드를 한 줄에 하나씩 입력해 주세요.");
      return;
    }
    if (keywords.length > MAX_KEYWORDS) {
      setError(`한 번에 최대 ${MAX_KEYWORDS}개까지 실행할 수 있어요. (현재 ${keywords.length}개)`);
      return;
    }

    let base: Date | null = null;
    if (registerMode === "future") {
      base = new Date(`${startDate}T${time}`);
      if (Number.isNaN(base.getTime())) {
        setError("시작일과 발행 시각을 확인해 주세요.");
        return;
      }
      if (base.getTime() <= Date.now()) {
        setError("첫 발행 시각이 이미 지났어요. 미래 시각으로 선택해 주세요.");
        return;
      }
    }

    const categoryName = cats.find((c) => c.id === categoryId)?.name;
    const schedule = (i: number) =>
      base ? new Date(base.getTime() + i * intervalDays * 24 * 60 * 60 * 1000) : null;

    cancelRef.current = false;
    setRunning(true);
    setItems(
      keywords.map((keyword, i) => {
        const when = schedule(i);
        return {
          keyword,
          state: "wait",
          scheduledFor: when ? when.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" }) : undefined,
        };
      }),
    );

    let doneCount = 0;
    let failCount = 0;

    for (let i = 0; i < keywords.length; i++) {
      if (cancelRef.current) {
        updateItem(i, { state: "skipped" });
        continue;
      }
      const keyword = keywords[i];
      try {
        updateItem(i, { state: "generating" });
        const { post } = await callWithRetry(
          () =>
            wpApi<{ post: GeneratedPost }>("/api/wp/generate", {
              json: { topic: keyword, categoryName, tone, length },
            }),
          () => cancelRef.current,
        );

        if (cancelRef.current) {
          updateItem(i, { state: "skipped" });
          continue;
        }

        updateItem(i, { state: "posting" });
        const when = schedule(i);
        const payload: Record<string, unknown> = {
          title: post.title,
          html: post.html,
          excerpt: post.excerpt,
          tags: post.tags,
          status: registerMode,
        };
        if (categoryId) payload.categoryId = categoryId;
        if (registerMode === "future" && when) payload.dateGmt = when.toISOString();

        const { post: created } = await callWithRetry(
          () =>
            wpApi<{ post: { id: number; link: string; dateGmt: string } }>("/api/wp/posts", {
              json: payload,
            }),
          () => cancelRef.current,
        );

        doneCount++;
        updateItem(i, {
          state: "done",
          link: created.link,
          scheduledFor:
            registerMode === "future" && created.dateGmt
              ? formatWpDate(created.dateGmt)
              : undefined,
        });
      } catch (e) {
        failCount++;
        updateItem(i, {
          state: "fail",
          error: e instanceof Error ? e.message : "알 수 없는 오류",
        });
      }
    }

    setRunning(false);
    const skipped = cancelRef.current ? keywords.length - doneCount - failCount : 0;
    setSummary(
      `완료 ${doneCount}건 · 실패 ${failCount}건${skipped > 0 ? ` · 중단 ${skipped}건` : ""} — ${
        registerMode === "future"
          ? "예약된 글은 워드프레스가 시각에 맞춰 자동 발행합니다."
          : "임시글은 발행 현황에서 [지금 발행]으로 올릴 수 있어요."
      }`,
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold">대량 자동화</h1>
      <p className="mt-1 text-sm text-slate-500">
        키워드마다 AI가 글을 쓰고, 정한 간격으로 {conn.siteName}에 예약 등록합니다.
      </p>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        {/* ── 좌: 설정 ── */}
        <section className="h-fit rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-2">
          <div className="space-y-4">
            <div>
              <label htmlFor="b-keywords" className="text-sm font-medium text-slate-700">
                키워드 목록 <span className="text-red-500">*</span>{" "}
                <span className="font-normal text-slate-400">
                  (한 줄에 하나, 최대 {MAX_KEYWORDS}개 — 현재 {keywords.length}개)
                </span>
              </label>
              <textarea
                id="b-keywords"
                value={keywordsText}
                onChange={(e) => setKeywordsText(e.target.value)}
                rows={7}
                disabled={running}
                placeholder={"소상공인 정부지원금 신청 방법\n마케팅 자동화 도구 비교\n네이버 블로그 상위노출 원리"}
                className="mt-1.5 w-full resize-y rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
              />
            </div>

            <div>
              <label htmlFor="b-cat" className="text-sm font-medium text-slate-700">
                카테고리
              </label>
              <select
                id="b-cat"
                value={categoryId}
                onChange={(e) => setCategoryId(Number(e.target.value))}
                disabled={running}
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
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
                <label htmlFor="b-tone" className="text-sm font-medium text-slate-700">
                  말투
                </label>
                <select
                  id="b-tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  disabled={running}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
                >
                  {TONES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="b-len" className="text-sm font-medium text-slate-700">
                  분량
                </label>
                <select
                  id="b-len"
                  value={length}
                  onChange={(e) => setLength(e.target.value as typeof length)}
                  disabled={running}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
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
              <span className="text-sm font-medium text-slate-700">등록 방식</span>
              <div className="mt-2 flex gap-4">
                <label className="flex items-center gap-1.5 text-sm text-slate-700">
                  <input
                    type="radio"
                    name="registerMode"
                    checked={registerMode === "future"}
                    onChange={() => setRegisterMode("future")}
                    disabled={running}
                    className="accent-indigo-600"
                  />
                  간격대로 예약 발행
                </label>
                <label className="flex items-center gap-1.5 text-sm text-slate-700">
                  <input
                    type="radio"
                    name="registerMode"
                    checked={registerMode === "draft"}
                    onChange={() => setRegisterMode("draft")}
                    disabled={running}
                    className="accent-indigo-600"
                  />
                  전부 임시글로
                </label>
              </div>
            </div>

            {registerMode === "future" && (
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label htmlFor="b-date" className="text-sm font-medium text-slate-700">
                    시작일
                  </label>
                  <input
                    id="b-date"
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    disabled={running}
                    className="mt-1.5 w-full rounded-lg border border-slate-300 px-2.5 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
                  />
                </div>
                <div>
                  <label htmlFor="b-time" className="text-sm font-medium text-slate-700">
                    발행 시각
                  </label>
                  <input
                    id="b-time"
                    type="time"
                    value={time}
                    onChange={(e) => setTime(e.target.value)}
                    disabled={running}
                    className="mt-1.5 w-full rounded-lg border border-slate-300 px-2.5 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
                  />
                </div>
                <div>
                  <label htmlFor="b-interval" className="text-sm font-medium text-slate-700">
                    간격
                  </label>
                  <select
                    id="b-interval"
                    value={intervalDays}
                    onChange={(e) => setIntervalDays(Number(e.target.value))}
                    disabled={running}
                    className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
                  >
                    {INTERVALS.map((iv) => (
                      <option key={iv.value} value={iv.value}>
                        {iv.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {error && <p className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600">{error}</p>}

            {running ? (
              <button
                onClick={() => {
                  cancelRef.current = true;
                }}
                className="w-full rounded-lg border border-red-300 bg-white px-5 py-3 text-sm font-semibold text-red-600 transition hover:bg-red-50"
              >
                중단하기 (진행 중인 글까지만 등록)
              </button>
            ) : (
              <button
                onClick={run}
                disabled={keywords.length === 0}
                className="w-full rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                자동화 시작 ({keywords.length}개 글)
              </button>
            )}

            <p className="text-xs leading-5 text-slate-400">
              실행 중에는 이 탭을 닫지 마세요. 등록이 끝난 뒤의 예약 발행은 워드프레스가 알아서
              처리합니다.
            </p>
          </div>
        </section>

        {/* ── 우: 진행 상황 ── */}
        <section className="rounded-2xl border border-slate-200 bg-white lg:col-span-3">
          <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
            <span className="font-semibold">진행 상황</span>
            {items.length > 0 && (
              <span className="text-sm text-slate-400">
                {items.filter((it) => it.state === "done").length}/{items.length} 완료
              </span>
            )}
          </header>

          {items.length === 0 ? (
            <p className="px-6 py-24 text-center text-sm text-slate-400">
              왼쪽에서 키워드를 입력하고 [자동화 시작]을 누르면
              <br />
              키워드별 진행 상황이 여기에 표시돼요.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((it, i) => (
                <li key={`${it.keyword}-${i}`} className="flex items-center gap-3 px-6 py-3">
                  <span
                    className={`inline-flex w-20 shrink-0 justify-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                      it.state === "done"
                        ? "bg-emerald-50 text-emerald-700"
                        : it.state === "fail"
                          ? "bg-red-50 text-red-600"
                          : it.state === "wait" || it.state === "skipped"
                            ? "bg-slate-100 text-slate-500"
                            : "bg-indigo-50 text-indigo-700"
                    }`}
                  >
                    {STATE_LABEL[it.state]}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">{it.keyword}</p>
                    {it.state === "fail" && it.error && (
                      <p className="truncate text-xs text-red-500">{it.error}</p>
                    )}
                    {it.state !== "fail" && it.scheduledFor && (
                      <p className="text-xs text-slate-400">예약: {it.scheduledFor}</p>
                    )}
                  </div>
                  {it.link && it.state === "done" && (
                    <a
                      href={it.link}
                      target="_blank"
                      rel="noreferrer"
                      className="shrink-0 text-xs font-medium text-indigo-600 hover:underline"
                    >
                      글 보기
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}

          {summary && (
            <div className="border-t border-slate-200 px-6 py-4">
              <p className="text-sm text-slate-700">{summary}</p>
              <Link
                href="/wordpress/posts"
                className="mt-2 inline-block text-sm font-medium text-indigo-600 hover:underline"
              >
                발행 현황에서 확인하기 →
              </Link>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
