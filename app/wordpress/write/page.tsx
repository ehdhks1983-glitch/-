"use client";

// app/wordpress/write/page.tsx  [업데이트 — 워드프레스 자동 발행 v2]
// AI 글쓰기: 주제 입력 → 초안 생성 → 수정 → 즉시/임시/예약 발행.
// v2: 글 유형, 내부 링크(내 사이트 기존 글), SEO 설정(슬러그·SEO 제목·메타 설명·키워드),
//     대표 이미지 업로드, 발행 전 품질 체크리스트, 블록 에디터 형식 저장, AI 활용 안내 문구.
// 본문 미리보기는 sanitizeWpHtml(허용 태그만 속성 없이 재조립 + 내부 링크만)을 거친 HTML만 렌더한다.

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import Link from "next/link";
import NotConnected from "@/components/wp/NotConnected";
import { useWpConnection, wpApi, wpUpload } from "@/lib/wp/clientStore";
import { sanitizeWpHtml, siteHostOf } from "@/lib/wp/sanitizeHtml";
import { assessPost } from "@/lib/wp/quality";
import {
  POST_TYPES,
  type GeneratedPost,
  type InternalLinkCandidate,
  type PostType,
  type WpCategory,
  type WpPostSummary,
} from "@/lib/wp/types";

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

const DISCLOSURE_HTML =
  "<p><em>이 글은 AI의 도움을 받아 초안을 작성하고 운영자가 검토·수정했습니다.</em></p>";

/** 본문 미리보기 타이포그래피(허용 태그에 맞춘 최소 스타일) */
const PREVIEW_CLASS =
  "text-sm leading-7 text-slate-800 [&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-xl [&_h2]:font-bold " +
  "[&_h3]:mt-5 [&_h3]:mb-1.5 [&_h3]:text-lg [&_h3]:font-semibold [&_h4]:mt-4 [&_h4]:font-semibold " +
  "[&_p]:my-3 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5 " +
  "[&_li]:my-1 [&_blockquote]:my-3 [&_blockquote]:border-l-4 [&_blockquote]:border-indigo-200 " +
  "[&_blockquote]:pl-3 [&_blockquote]:text-slate-600 [&_a]:text-indigo-600 [&_a]:underline";

const INPUT_CLASS =
  "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none";

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
  const [postType, setPostType] = useState<PostType>("info");
  const [tone, setTone] = useState(TONES[0]);
  const [length, setLength] = useState<(typeof LENGTHS)[number]["value"]>("medium");
  const [extra, setExtra] = useState("");
  const [useLinks, setUseLinks] = useState(true);

  // 초안
  const [draft, setDraft] = useState<GeneratedPost | null>(null);
  const [tagsText, setTagsText] = useState("");
  const [showHtml, setShowHtml] = useState(false);
  const [featured, setFeatured] = useState<{ id: number; url: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [linkCandidates, setLinkCandidates] = useState<InternalLinkCandidate[] | null>(null);

  // 발행 옵션
  const [publishMode, setPublishMode] = useState<PublishMode>("publish");
  const [scheduleAt, setScheduleAt] = useState(defaultScheduleValue());
  const [useBlocks, setUseBlocks] = useState(true);
  const [addDisclosure, setAddDisclosure] = useState(false);

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

  const siteHost = conn ? siteHostOf(conn.url) : null;

  const previewHtml = useMemo(
    () => (draft ? sanitizeWpHtml(draft.html, { allowLinkHosts: siteHost ? [siteHost] : [] }) : ""),
    [draft, siteHost],
  );

  const tags = useMemo(
    () => tagsText.split(",").map((t) => t.trim()).filter(Boolean),
    [tagsText],
  );

  const report = useMemo(
    () =>
      draft
        ? assessPost({
            title: draft.title,
            html: draft.html,
            excerpt: draft.excerpt,
            tags,
            slug: draft.slug,
            metaDescription: draft.metaDescription,
            keyword: topic,
            hasFeaturedImage: featured !== null,
          })
        : null,
    [draft, tags, topic, featured],
  );

  if (conn === undefined) {
    return <p className="py-20 text-center text-sm text-slate-400">불러오는 중…</p>;
  }
  if (!conn) return <NotConnected />;

  async function loadLinkCandidates(): Promise<InternalLinkCandidate[]> {
    if (linkCandidates) return linkCandidates;
    try {
      const { posts } = await wpApi<{ posts: WpPostSummary[] }>(
        "/api/wp/posts?status=publish&per_page=30",
      );
      const list = posts.filter((p) => p.link).map((p) => ({ title: p.title, url: p.link }));
      setLinkCandidates(list);
      return list;
    } catch {
      setLinkCandidates([]);
      return [];
    }
  }

  async function generate() {
    setError("");
    setDone(null);
    setGenerating(true);
    try {
      const categoryName = cats.find((c) => c.id === categoryId)?.name;
      const internalLinks = useLinks ? await loadLinkCandidates() : [];
      const { post } = await wpApi<{ post: GeneratedPost }>("/api/wp/generate", {
        json: { topic, categoryName, tone, length, extra, postType, internalLinks },
      });
      setDraft(post);
      setTagsText(post.tags.join(", "));
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성에 실패했어요.");
    } finally {
      setGenerating(false);
    }
  }

  async function onPickImage(e: ChangeEvent<HTMLInputElement>) {
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;
    setError("");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("altText", draft?.title || topic);
      fd.append("title", draft?.title || topic);
      const { media } = await wpUpload<{ media: { id: number; url: string } }>("/api/wp/media", fd);
      setFeatured(media);
    } catch (err) {
      setError(err instanceof Error ? err.message : "이미지 업로드에 실패했어요.");
    } finally {
      setUploading(false);
      input.value = "";
    }
  }

  async function publish() {
    if (!draft) return;
    setError("");
    setPublishing(true);
    try {
      const payload: Record<string, unknown> = {
        title: draft.title,
        html: addDisclosure ? `${draft.html}${DISCLOSURE_HTML}` : draft.html,
        excerpt: draft.excerpt,
        tags,
        status: publishMode,
        slug: draft.slug,
        seoTitle: draft.seoTitle,
        metaDescription: draft.metaDescription,
        focusKeyword: draft.focusKeyword,
        format: useBlocks ? "blocks" : "classic",
      };
      if (categoryId) payload.categoryId = categoryId;
      if (featured) payload.featuredMediaId = featured.id;
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
    setFeatured(null);
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

            <div className="grid grid-cols-2 gap-3">
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
                  <option value={0}>선택 안 함</option>
                  {cats.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.count})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="w-type" className="text-sm font-medium text-slate-700">
                  글 유형
                </label>
                <select
                  id="w-type"
                  value={postType}
                  onChange={(e) => setPostType(e.target.value as PostType)}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
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

            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={useLinks}
                onChange={(e) => setUseLinks(e.target.checked)}
                className="mt-0.5 accent-indigo-600"
              />
              <span>
                내 사이트 기존 글로 <b>내부 링크</b> 넣기
                <span className="block text-xs text-slate-400">
                  발행된 글 최대 30개 중 관련 글 1~2개를 본문에 자연스럽게 연결해요.
                </span>
              </span>
            </label>

            <button
              onClick={generate}
              disabled={generating || topic.trim().length < 2}
              className="w-full rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? "초안 작성 중… (최대 1분)" : draft ? "다시 생성" : "AI 초안 생성"}
            </button>
          </div>
        </section>

        {/* ── 우: 초안 + SEO + 발행 ── */}
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
                    // 허용 태그만 속성 없이 재조립 + 내 사이트 링크만 허용(sanitizeWpHtml) — XSS 벡터 없음
                    dangerouslySetInnerHTML={{ __html: previewHtml }}
                  />
                )}
              </div>

              <div className="grid gap-4 px-6 py-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="w-excerpt" className="text-xs font-medium text-slate-400">
                    요약 (목록 노출)
                  </label>
                  <textarea
                    id="w-excerpt"
                    value={draft.excerpt}
                    onChange={(e) => setDraft({ ...draft, excerpt: e.target.value })}
                    maxLength={300}
                    rows={3}
                    className={`${INPUT_CLASS} resize-y`}
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
                    className={`${INPUT_CLASS} resize-y`}
                  />
                </div>
              </div>

              {/* SEO 설정 */}
              <div className="px-6 py-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">SEO 설정</span>
                  <span className="text-xs text-slate-400">
                    {conn.seoPlugin
                      ? `${conn.seoPlugin === "yoast" ? "Yoast" : conn.seoPlugin === "rankmath" ? "Rank Math" : "AIOSEO"}로 전송`
                      : "슬러그·요약만 반영(플러그인 없음)"}
                  </span>
                </div>
                <div className="mt-2 grid gap-3 sm:grid-cols-2">
                  <div>
                    <label htmlFor="w-slug" className="text-xs text-slate-500">
                      슬러그(URL) — 영문 소문자·숫자·하이픈
                    </label>
                    <input
                      id="w-slug"
                      type="text"
                      value={draft.slug}
                      onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
                      maxLength={70}
                      placeholder="비우면 제목으로 자동 생성"
                      className={`${INPUT_CLASS} font-mono text-xs`}
                    />
                  </div>
                  <div>
                    <label htmlFor="w-kw" className="text-xs text-slate-500">
                      핵심 키워드
                    </label>
                    <input
                      id="w-kw"
                      type="text"
                      value={draft.focusKeyword}
                      onChange={(e) => setDraft({ ...draft, focusKeyword: e.target.value })}
                      maxLength={60}
                      className={INPUT_CLASS}
                    />
                  </div>
                  <div>
                    <label htmlFor="w-seotitle" className="text-xs text-slate-500">
                      SEO 제목 ({draft.seoTitle.length}/60)
                    </label>
                    <input
                      id="w-seotitle"
                      type="text"
                      value={draft.seoTitle}
                      onChange={(e) => setDraft({ ...draft, seoTitle: e.target.value })}
                      maxLength={70}
                      className={INPUT_CLASS}
                    />
                  </div>
                  <div>
                    <label htmlFor="w-meta" className="text-xs text-slate-500">
                      메타 설명 ({draft.metaDescription.length}/155)
                    </label>
                    <textarea
                      id="w-meta"
                      value={draft.metaDescription}
                      onChange={(e) => setDraft({ ...draft, metaDescription: e.target.value })}
                      maxLength={160}
                      rows={2}
                      className={`${INPUT_CLASS} resize-y`}
                    />
                  </div>
                </div>
              </div>

              {/* 대표 이미지 */}
              <div className="px-6 py-4">
                <span className="text-xs font-medium text-slate-400">대표 이미지 (선택)</span>
                <div className="mt-2 flex items-center gap-4">
                  {featured ? (
                    // eslint-disable-next-line @next/next/no-img-element -- 사용자 WP 사이트의 외부 이미지(도메인 미리 알 수 없음)
                    <img
                      src={featured.url}
                      alt="대표 이미지 미리보기"
                      className="h-20 w-32 rounded-lg border border-slate-200 object-cover"
                    />
                  ) : (
                    <div className="flex h-20 w-32 items-center justify-center rounded-lg border border-dashed border-slate-300 text-xs text-slate-400">
                      없음
                    </div>
                  )}
                  <div className="space-y-1.5">
                    <label className="inline-block cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50">
                      {uploading ? "업로드 중…" : featured ? "다른 이미지" : "이미지 올리기"}
                      <input
                        type="file"
                        accept="image/jpeg,image/png,image/webp,image/gif"
                        onChange={onPickImage}
                        disabled={uploading}
                        className="hidden"
                      />
                    </label>
                    {featured && (
                      <button
                        onClick={() => setFeatured(null)}
                        className="block text-xs text-red-500 hover:underline"
                      >
                        대표 이미지 해제
                      </button>
                    )}
                    <p className="text-xs text-slate-400">JPG·PNG·WEBP·GIF, 8MB 이하. 워드프레스 미디어에 바로 올라가요.</p>
                  </div>
                </div>
              </div>

              {/* 발행 전 체크리스트 */}
              {report && (
                <div className="px-6 py-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-400">발행 전 품질 체크</span>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        report.passed >= report.total - 2
                          ? "bg-emerald-50 text-emerald-700"
                          : report.passed >= report.total / 2
                            ? "bg-amber-50 text-amber-700"
                            : "bg-red-50 text-red-600"
                      }`}
                    >
                      {report.passed}/{report.total}
                    </span>
                  </div>
                  <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
                    {report.checks.map((c) => (
                      <li key={c.key} className="flex items-start gap-2 text-xs">
                        <span className={c.ok ? "text-emerald-600" : "text-slate-300"}>{c.ok ? "✓" : "○"}</span>
                        <span className={c.ok ? "text-slate-600" : "text-slate-700"}>
                          {c.label}
                          {!c.ok && <span className="block text-slate-400">{c.hint}</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-slate-400">
                    검색엔진은 생산 방식과 무관하게 &lsquo;독자 가치 없는 대량 글&rsquo;을 걸러요. 체크가 많이
                    비면 내용을 보강한 뒤 올리는 걸 권해요.
                  </p>
                </div>
              )}

              {/* 발행 방법 + 옵션 */}
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
                <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-600">
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={useBlocks}
                      onChange={(e) => setUseBlocks(e.target.checked)}
                      className="accent-indigo-600"
                    />
                    블록 에디터 형식으로 저장 (권장)
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={addDisclosure}
                      onChange={(e) => setAddDisclosure(e.target.checked)}
                      className="accent-indigo-600"
                    />
                    글 끝에 AI 활용 안내 문구 추가
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-between gap-3 px-6 py-4">
                <p className="min-h-5 text-sm text-red-600">{error}</p>
                <button
                  onClick={publish}
                  disabled={publishing || uploading || !draft.title.trim()}
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
