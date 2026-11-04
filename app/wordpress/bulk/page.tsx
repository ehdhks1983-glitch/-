"use client";

// app/wordpress/bulk/page.tsx  [업데이트 — 워드프레스 자동 발행 v2]
// 대량 자동화: 키워드 여러 개 → 키워드마다 AI 글 생성 → 검토용 임시글(권장) 또는 간격 예약 발행.
// v2(조사 반영): 검색엔진의 '대량 생산형 저품질 콘텐츠' 정책 → 기본값을 "임시글로 저장 후 검토"로,
//     이미 있는 주제는 건너뛰고(중복 검사), 내부 링크·SEO 메타·블록 형식을 자동 적용한다.
// 브라우저가 순차 실행하며 진행 상황을 보여준다. 등록이 끝난 뒤에는 탭을 닫아도 예약은 유지된다.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import NotConnected from "@/components/wp/NotConnected";
import { useWpConnection, wpApi, WpApiClientError, formatWpDate } from "@/lib/wp/clientStore";
import { findDuplicateTopic } from "@/lib/wp/quality";
import {
  POST_TYPES,
  type GeneratedPost,
  type InternalLinkCandidate,
  type PostType,
  type WpCategory,
  type WpPostSummary,
} from "@/lib/wp/types";

type ItemState = "wait" | "generating" | "posting" | "done" | "fail" | "skipped" | "duplicate";

interface BulkItem {
  keyword: string;
  state: ItemState;
  scheduledFor?: string; // 로컬 표시용
  link?: string;
  error?: string;
  note?: string;
}

const MAX_KEYWORDS = 20;
/** 429(속도 제한) 재시도 대기(ms)와 횟수 */
const RETRY_WAIT_MS = 15_000;
const MAX_RETRIES = 4;
/** 중복 검사에 쓸 기존 글 제목 수(최신순) */
const EXISTING_TITLES_PAGES = 2;

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
  duplicate: "중복 건너뜀",
};

const SELECT_CLASS =
  "mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50";

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
  const [postType, setPostType] = useState<PostType>("info");
  const [tone, setTone] = useState(TONES[0]);
  const [length, setLength] = useState<(typeof LENGTHS)[number]["value"]>("medium");
  const [registerMode, setRegisterMode] = useState<"draft" | "future">("draft");
  const [startDate, setStartDate] = useState(tomorrowDate());
  const [time, setTime] = useState("09:00");
  const [intervalDays, setIntervalDays] = useState(1);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [useLinks, setUseLinks] = useState(true);

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

  /** 기존 글 제목(중복 검사용)과 발행 글(내부 링크용)을 한 번에 가져온다 */
  async function loadExisting(): Promise<{ titles: string[]; links: InternalLinkCandidate[] }> {
    const titles: string[] = [];
    const links: InternalLinkCandidate[] = [];
    for (let page = 1; page <= EXISTING_TITLES_PAGES; page++) {
      try {
        const { posts, totalPages } = await wpApi<{ posts: WpPostSummary[]; totalPages: number }>(
          `/api/wp/posts?status=all&per_page=50&page=${page}`,
        );
        for (const p of posts) {
          titles.push(p.title);
          if (p.status === "publish" && p.link && links.length < 30) {
            links.push({ title: p.title, url: p.link });
          }
        }
        if (page >= totalPages) break;
      } catch {
        break; // 조회 실패 시 지금까지 모은 것만 사용
      }
    }
    return { titles, links };
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
          scheduledFor: when
            ? when.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" })
            : undefined,
        };
      }),
    );

    const existing = skipDuplicates || useLinks ? await loadExisting() : { titles: [], links: [] };
    const internalLinks = useLinks ? existing.links : [];

    let doneCount = 0;
    let failCount = 0;
    let dupCount = 0;
    let slot = 0; // 중복으로 건너뛴 키워드는 예약 슬롯을 차지하지 않는다

    for (let i = 0; i < keywords.length; i++) {
      if (cancelRef.current) {
        updateItem(i, { state: "skipped" });
        continue;
      }
      const keyword = keywords[i];

      if (skipDuplicates) {
        const dup = findDuplicateTopic(keyword, existing.titles);
        if (dup) {
          dupCount++;
          updateItem(i, { state: "duplicate", note: `이미 있는 글: ${dup}`, scheduledFor: undefined });
          continue;
        }
      }

      try {
        updateItem(i, { state: "generating" });
        const { post } = await callWithRetry(
          () =>
            wpApi<{ post: GeneratedPost }>("/api/wp/generate", {
              json: { topic: keyword, categoryName, tone, length, postType, internalLinks },
            }),
          () => cancelRef.current,
        );

        if (cancelRef.current) {
          updateItem(i, { state: "skipped" });
          continue;
        }

        updateItem(i, { state: "posting" });
        const when = schedule(slot);
        const payload: Record<string, unknown> = {
          title: post.title,
          html: post.html,
          excerpt: post.excerpt,
          tags: post.tags,
          status: registerMode,
          slug: post.slug,
          seoTitle: post.seoTitle,
          metaDescription: post.metaDescription,
          focusKeyword: post.focusKeyword,
          format: "blocks",
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
        slot++;
        existing.titles.push(post.title); // 같은 실행 안에서의 중복도 방지
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
    const skipped = cancelRef.current ? keywords.length - doneCount - failCount - dupCount : 0;
    setSummary(
      `완료 ${doneCount}건 · 실패 ${failCount}건${dupCount ? ` · 중복 건너뜀 ${dupCount}건` : ""}${
        skipped > 0 ? ` · 중단 ${skipped}건` : ""
      } — ${
        registerMode === "future"
          ? "예약된 글은 워드프레스가 시각에 맞춰 자동 발행합니다."
          : "임시글은 발행 현황이나 워드프레스 편집 화면에서 검토 후 발행하세요."
      }`,
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold">대량 자동화</h1>
      <p className="mt-1 text-sm text-slate-500">
        키워드마다 AI가 글을 쓰고, {conn.siteName}에 검토용 임시글 또는 간격 예약으로 등록합니다.
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

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="b-cat" className="text-sm font-medium text-slate-700">
                  카테고리
                </label>
                <select
                  id="b-cat"
                  value={categoryId}
                  onChange={(e) => setCategoryId(Number(e.target.value))}
                  disabled={running}
                  className={SELECT_CLASS}
                >
                  <option value={0}>선택 안 함</option>
                  {cats.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.count})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="b-type" className="text-sm font-medium text-slate-700">
                  글 유형
                </label>
                <select
                  id="b-type"
                  value={postType}
                  onChange={(e) => setPostType(e.target.value as PostType)}
                  disabled={running}
                  className={SELECT_CLASS}
                >
                  {(Object.keys(POST_TYPES) as PostType[]).map((t) => (
                    <option key={t} value={t}>
                      {POST_TYPES[t].label}
                    </option>
                  ))}
                </select>
              </div>
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
                  className={SELECT_CLASS}
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
                  className={SELECT_CLASS}
                >
                  {LENGTHS.map((l) => (
                    <option key={l.value} value={l.value}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-2 text-sm text-slate-700">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={skipDuplicates}
                  onChange={(e) => setSkipDuplicates(e.target.checked)}
                  disabled={running}
                  className="accent-indigo-600"
                />
                이미 비슷한 글이 있으면 건너뛰기 (중복 방지)
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={useLinks}
                  onChange={(e) => setUseLinks(e.target.checked)}
                  disabled={running}
                  className="accent-indigo-600"
                />
                기존 글로 내부 링크 넣기
              </label>
            </div>

            <div>
              <span className="text-sm font-medium text-slate-700">등록 방식</span>
              <div className="mt-2 space-y-2">
                <label className="flex items-start gap-2 text-sm text-slate-700">
                  <input
                    type="radio"
                    name="registerMode"
                    checked={registerMode === "draft"}
                    onChange={() => setRegisterMode("draft")}
                    disabled={running}
                    className="mt-0.5 accent-indigo-600"
                  />
                  <span>
                    임시글로 저장 → 검토 후 발행 <span className="text-xs font-semibold text-emerald-600">권장</span>
                    <span className="block text-xs text-slate-400">
                      한 번 훑어보고 올리는 습관이 검색 노출에 유리해요.
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2 text-sm text-slate-700">
                  <input
                    type="radio"
                    name="registerMode"
                    checked={registerMode === "future"}
                    onChange={() => setRegisterMode("future")}
                    disabled={running}
                    className="mt-0.5 accent-indigo-600"
                  />
                  <span>
                    간격대로 바로 예약 발행
                    <span className="block text-xs text-slate-400">
                      검토 없이 자동 공개돼요. 하루 1~2개 간격을 권장합니다.
                    </span>
                  </span>
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
                    className={SELECT_CLASS}
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

        {/* ── 우: 안내 + 진행 상황 ── */}
        <div className="space-y-4 lg:col-span-3">
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-xs leading-5 text-amber-800">
            <b>검색 정책 한 줄 요약 (2026)</b> — 구글은 AI든 사람이든 &lsquo;독자 가치 없이 양만 늘린
            글&rsquo;을 스팸으로 분류하고 2026년 업데이트들에서 단속을 강화했어요. 그래서 이 도구는{" "}
            <b>중복 주제 건너뛰기 · 내부 링크 · SEO 메타 · 품질 체크</b>를 자동으로 넣고, 기본값을
            &lsquo;임시글로 저장 후 검토&rsquo;로 둡니다. 하루 수십 개씩 쏟아내기보다 꾸준히 좋은 글을 올리는
            쪽이 결과가 좋아요.
          </div>

          <section className="rounded-2xl border border-slate-200 bg-white">
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
                      className={`inline-flex w-24 shrink-0 justify-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                        it.state === "done"
                          ? "bg-emerald-50 text-emerald-700"
                          : it.state === "fail"
                            ? "bg-red-50 text-red-600"
                            : it.state === "duplicate"
                              ? "bg-amber-50 text-amber-700"
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
                      {it.state === "duplicate" && it.note && (
                        <p className="truncate text-xs text-amber-600">{it.note}</p>
                      )}
                      {it.state !== "fail" && it.state !== "duplicate" && it.scheduledFor && (
                        <p className="text-xs text-slate-400">예약: {it.scheduledFor}</p>
                      )}
                    </div>
                    {it.link && it.state === "done" && registerMode === "future" && (
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
    </div>
  );
}
