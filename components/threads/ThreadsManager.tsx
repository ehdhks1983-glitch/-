// components/threads/ThreadsManager.tsx  [신규] — Threads 자동발행 콘솔(클라이언트).
// 흐름: 계정 연결 → AI 초안 생성 → 사람이 검토/수정 → 초안 저장 또는 예약/지금 발행 → 큐에서 관리.
// 모든 발행은 공식 API 경유(서버 라우트). 이 컴포넌트는 토큰을 절대 다루지 않는다.

"use client";

import { useState } from "react";
import type { ThreadsPostRow, ThreadsPostStatus } from "@/lib/threads/db";

interface AccountInfo {
  username: string;
  threads_user_id: string;
  token_expires_at: string | null;
}

interface Props {
  threadsReady: boolean;
  maxText: number;
  dailyCap: number;
  metaDailyLimit: number;
  initialAccount: AccountInfo | null;
  initialPosts: ThreadsPostRow[];
  publishedToday: number;
  notice: string | null;
}

interface ApiResult<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
}

async function api<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const data = (await res.json().catch(() => null)) as (T & { error?: string }) | null;
    if (!res.ok) return { ok: false, data: null, error: data?.error ?? "요청에 실패했어요." };
    return { ok: true, data: data as T, error: null };
  } catch {
    return { ok: false, data: null, error: "네트워크 오류예요. 잠시 후 다시 시도해 주세요." };
  }
}

export default function ThreadsManager(props: Props) {
  const { threadsReady, maxText, dailyCap, metaDailyLimit } = props;

  const [account, setAccount] = useState<AccountInfo | null>(props.initialAccount);
  const [posts, setPosts] = useState<ThreadsPostRow[]>(props.initialPosts);
  const [publishedToday, setPublishedToday] = useState(props.publishedToday);

  const [topic, setTopic] = useState("");
  const [tone, setTone] = useState("친근하고 진솔한");
  const [count, setCount] = useState(3);
  const [drafts, setDrafts] = useState<{ id: string; text: string }[]>([]);

  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(initialNotice(props.notice));
  const [err, setErr] = useState<string | null>(null);

  const flash = (m: string) => {
    setMsg(m);
    setErr(null);
  };
  const fail = (m: string) => {
    setErr(m);
    setMsg(null);
  };

  async function refresh() {
    const [a, p] = await Promise.all([
      api<{ publishedToday: number; account: AccountInfo | null }>("/api/threads/account"),
      api<{ posts: ThreadsPostRow[] }>("/api/threads/posts"),
    ]);
    if (a.ok && a.data) {
      setPublishedToday(a.data.publishedToday);
      setAccount(a.data.account);
    }
    if (p.ok && p.data) setPosts(p.data.posts);
  }

  async function generate() {
    if (!topic.trim()) return fail("어떤 주제로 쓸지 적어 주세요.");
    setBusy(true);
    const r = await api<{ drafts: string[] }>("/api/threads/drafts", {
      method: "POST",
      body: JSON.stringify({ topic, tone, count }),
    });
    setBusy(false);
    if (!r.ok || !r.data) return fail(r.error ?? "초안 생성 실패");
    setDrafts(r.data.drafts.map((text) => ({ id: crypto.randomUUID(), text })));
    flash(`초안 ${r.data.drafts.length}개 생성됐어요. 검토 후 저장하거나 예약하세요.`);
  }

  function removeDraft(id: string) {
    setDrafts((d) => d.filter((x) => x.id !== id));
  }

  /** 초안 저장(draft) 또는 예약(scheduled). img 가 있으면 IMAGE 글로 저장. 성공 시 큐 반영 + 초안 제거. */
  async function savePost(
    draftId: string,
    text: string,
    img: string,
    opts: { schedule?: string | null },
  ): Promise<ThreadsPostRow | null> {
    const body: Record<string, unknown> = { text };
    const imageUrl = img.trim();
    if (imageUrl) {
      body.mediaType = "IMAGE";
      body.imageUrl = imageUrl;
    }
    if (opts.schedule) {
      body.status = "scheduled";
      body.scheduledAt = opts.schedule;
    } else {
      body.status = "draft";
    }
    const r = await api<{ post: ThreadsPostRow }>("/api/threads/posts", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!r.ok || !r.data) {
      fail(r.error ?? "저장 실패");
      return null;
    }
    setPosts((p) => [r.data!.post, ...p]);
    removeDraft(draftId);
    return r.data.post;
  }

  async function onSaveDraft(draftId: string, text: string, img: string) {
    setBusy(true);
    const post = await savePost(draftId, text, img, {});
    setBusy(false);
    if (post) flash("초안으로 저장했어요.");
  }

  async function onSchedule(draftId: string, text: string, img: string, localValue: string) {
    const iso = toIso(localValue);
    if (!iso) return fail("예약 시각을 현재 이후로 정해 주세요.");
    setBusy(true);
    const post = await savePost(draftId, text, img, { schedule: iso });
    setBusy(false);
    if (post) flash("예약했어요. 예약 시각에 자동 발행됩니다(크론 필요).");
  }

  async function onPublishDraftNow(draftId: string, text: string, img: string) {
    setBusy(true);
    const post = await savePost(draftId, text, img, {});
    if (post) await publishNow(post.id);
    setBusy(false);
  }

  async function publishNow(postId: string) {
    const r = await api<{ post: ThreadsPostRow }>(`/api/threads/posts/${postId}/publish`, {
      method: "POST",
    });
    if (!r.ok || !r.data) return fail(r.error ?? "발행 실패");
    upsertPost(r.data.post);
    setPublishedToday((n) => n + 1);
    flash("발행했어요! 🎉");
  }

  async function cancelPost(postId: string) {
    const r = await api<{ post: ThreadsPostRow }>(`/api/threads/posts/${postId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "canceled" }),
    });
    if (!r.ok || !r.data) return fail(r.error ?? "취소 실패");
    upsertPost(r.data.post);
    flash("예약을 취소했어요.");
  }

  async function deletePost(postId: string) {
    const r = await api<{ ok: boolean }>(`/api/threads/posts/${postId}`, { method: "DELETE" });
    if (!r.ok) return fail(r.error ?? "삭제 실패");
    setPosts((p) => p.filter((x) => x.id !== postId));
  }

  function upsertPost(post: ThreadsPostRow) {
    setPosts((p) => p.map((x) => (x.id === post.id ? post : x)));
  }

  async function disconnect() {
    if (!confirm("Threads 계정 연결을 해제할까요? 저장된 큐는 유지됩니다.")) return;
    setBusy(true);
    const r = await api<{ ok: boolean }>("/api/threads/account", { method: "DELETE" });
    setBusy(false);
    if (!r.ok) return fail(r.error ?? "연결 해제 실패");
    setAccount(null);
    flash("연결을 해제했어요.");
  }

  const capReached = publishedToday >= dailyCap;

  return (
    <div className="space-y-6">
      {msg && <Banner kind="ok" text={msg} onClose={() => setMsg(null)} />}
      {err && <Banner kind="err" text={err} onClose={() => setErr(null)} />}

      {/* 계정 카드 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        {account ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                  연결됨
                </span>
                <span className="font-semibold">@{account.username || account.threads_user_id}</span>
              </div>
              <p className="mt-1 text-sm text-slate-500">
                오늘 발행 {publishedToday}/{dailyCap}
                <span className="text-slate-400"> (Meta 상한 {metaDailyLimit})</span>
                {account.token_expires_at && (
                  <span className="ml-2 text-slate-400">· 토큰 만료 {fmtDate(account.token_expires_at)}</span>
                )}
              </p>
            </div>
            <button
              onClick={disconnect}
              disabled={busy}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50 disabled:opacity-50"
            >
              연결 해제
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">Threads 계정 연결</h2>
              <p className="mt-1 text-sm text-slate-500">
                공식 Threads API로 내 계정에 발행해요. 모르는 사람을 팔로우/조작하지 않습니다.
              </p>
            </div>
            {threadsReady ? (
              <a
                href="/api/threads/connect"
                className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
              >
                Threads 연결하기
              </a>
            ) : (
              <span className="rounded-full bg-amber-100 px-3 py-2 text-xs font-medium text-amber-700">
                연동 키 미설정 (.env)
              </span>
            )}
          </div>
        )}
      </section>

      {/* 초안 생성기 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold">AI 초안 생성</h2>
        <p className="mt-1 text-sm text-slate-500">
          주제만 적으면 초안을 만들어요. <b>발행은 형이 검토하고 누를 때만</b> 됩니다.
        </p>
        <div className="mt-4 space-y-3">
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            rows={2}
            placeholder="예: 1인 자영업 운영하며 배운 점, 오늘 가게에서 있었던 일…"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
          />
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              placeholder="톤 (예: 친근하고 진솔한)"
              className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            />
            <select
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}개
                </option>
              ))}
            </select>
            <button
              onClick={generate}
              disabled={busy}
              className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {busy ? "생성 중…" : "초안 생성"}
            </button>
          </div>
        </div>

        {drafts.length > 0 && (
          <div className="mt-5 space-y-3">
            {drafts.map((d) => (
              <DraftCard
                key={d.id}
                initialText={d.text}
                maxText={maxText}
                busy={busy}
                canPublish={Boolean(account) && !capReached}
                onSaveDraft={(text, img) => onSaveDraft(d.id, text, img)}
                onSchedule={(text, img, val) => onSchedule(d.id, text, img, val)}
                onPublishNow={(text, img) => onPublishDraftNow(d.id, text, img)}
                onDiscard={() => removeDraft(d.id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* 발행 큐 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">발행 큐</h2>
          <button onClick={refresh} className="text-sm text-slate-500 underline-offset-2 hover:underline">
            새로고침
          </button>
        </div>
        {posts.length === 0 ? (
          <p className="mt-4 rounded-xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-400">
            아직 저장한 글이 없어요. 위에서 초안을 만들어 보세요.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {posts.map((p) => (
              <QueueItem
                key={p.id}
                post={p}
                canPublish={Boolean(account) && !capReached}
                onPublishNow={() => publishNow(p.id)}
                onCancel={() => cancelPost(p.id)}
                onDelete={() => deletePost(p.id)}
              />
            ))}
          </ul>
        )}
        {capReached && account && (
          <p className="mt-3 text-xs text-amber-600">
            오늘 발행 한도({dailyCap})에 도달했어요. 예약은 가능하고, 한도가 풀리면 자동 발행됩니다.
          </p>
        )}
      </section>
    </div>
  );
}

// ───────────────────────── 초안 카드 ─────────────────────────

function DraftCard(props: {
  initialText: string;
  maxText: number;
  busy: boolean;
  canPublish: boolean;
  onSaveDraft: (text: string, img: string) => void;
  onSchedule: (text: string, img: string, localValue: string) => void;
  onPublishNow: (text: string, img: string) => void;
  onDiscard: () => void;
}) {
  const [text, setText] = useState(props.initialText);
  const [img, setImg] = useState("");
  const [when, setWhen] = useState("");
  const over = text.length > props.maxText;
  const imgBad = img.trim() !== "" && !/^https?:\/\//i.test(img.trim());
  const disabled = props.busy || over || imgBad || !text.trim();

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
      />
      <div className="mt-1 flex items-center justify-between text-xs">
        <span className={over ? "text-red-500" : "text-slate-400"}>
          {text.length}/{props.maxText}
        </span>
        <button onClick={props.onDiscard} className="text-slate-400 hover:text-slate-600">
          버리기
        </button>
      </div>
      <input
        type="url"
        value={img}
        onChange={(e) => setImg(e.target.value)}
        placeholder="이미지 URL (선택) — 공개 https 주소"
        className={`mt-2 w-full rounded-lg border bg-white px-3 py-1.5 text-sm outline-none ${
          imgBad ? "border-red-300 focus:border-red-400" : "border-slate-200 focus:border-slate-400"
        }`}
      />
      {imgBad && (
        <p className="mt-1 text-xs text-red-500">http(s):// 로 시작하는 공개 이미지 주소를 입력해 주세요.</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          onClick={() => props.onSaveDraft(text, img)}
          disabled={disabled}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium transition hover:bg-slate-100 disabled:opacity-50"
        >
          초안 저장
        </button>
        <input
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
        />
        <button
          onClick={() => props.onSchedule(text, img, when)}
          disabled={disabled || !when}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium transition hover:bg-slate-100 disabled:opacity-50"
        >
          예약
        </button>
        <button
          onClick={() => props.onPublishNow(text, img)}
          disabled={disabled || !props.canPublish}
          title={!props.canPublish ? "계정 연결 및 일일 한도 확인" : ""}
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
        >
          지금 발행
        </button>
      </div>
    </div>
  );
}

// ───────────────────────── 큐 아이템 ─────────────────────────

function QueueItem(props: {
  post: ThreadsPostRow;
  canPublish: boolean;
  onPublishNow: () => void;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const { post } = props;
  const canPublishThis =
    post.status === "draft" || post.status === "scheduled" || post.status === "failed";

  return (
    <li className="rounded-xl border border-slate-200 p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="whitespace-pre-wrap text-sm text-slate-800">{post.text}</p>
        <StatusBadge status={post.status} />
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-slate-400">
          {post.media_type === "IMAGE" && "🖼 이미지 · "}
          {post.status === "scheduled" && post.scheduled_at && `예약: ${fmtDate(post.scheduled_at)}`}
          {post.status === "published" && post.published_at && `발행: ${fmtDate(post.published_at)}`}
          {post.status === "failed" && post.error && `오류: ${post.error}`}
        </span>
        <div className="flex flex-wrap gap-2 text-sm">
          {canPublishThis && (
            <button
              onClick={props.onPublishNow}
              disabled={!props.canPublish}
              title={!props.canPublish ? "계정 연결 및 일일 한도 확인" : ""}
              className="rounded-lg bg-slate-900 px-3 py-1 font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
            >
              지금 발행
            </button>
          )}
          {post.status === "scheduled" && (
            <button
              onClick={props.onCancel}
              className="rounded-lg border border-slate-200 px-3 py-1 font-medium transition hover:bg-slate-50"
            >
              예약 취소
            </button>
          )}
          <button
            onClick={props.onDelete}
            className="rounded-lg border border-slate-200 px-3 py-1 font-medium text-red-600 transition hover:bg-red-50"
          >
            삭제
          </button>
        </div>
      </div>
    </li>
  );
}

function StatusBadge({ status }: { status: ThreadsPostStatus }) {
  const map: Record<ThreadsPostStatus, { label: string; cls: string }> = {
    draft: { label: "초안", cls: "bg-slate-100 text-slate-600" },
    scheduled: { label: "예약", cls: "bg-indigo-100 text-indigo-700" },
    publishing: { label: "발행중", cls: "bg-amber-100 text-amber-700" },
    published: { label: "발행됨", cls: "bg-emerald-100 text-emerald-700" },
    failed: { label: "실패", cls: "bg-red-100 text-red-700" },
    canceled: { label: "취소", cls: "bg-slate-100 text-slate-400" },
  };
  const s = map[status];
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>;
}

function Banner({ kind, text, onClose }: { kind: "ok" | "err"; text: string; onClose: () => void }) {
  const cls = kind === "ok" ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-red-50 text-red-800 border-red-200";
  return (
    <div className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm ${cls}`}>
      <span>{text}</span>
      <button onClick={onClose} className="opacity-60 hover:opacity-100">
        ✕
      </button>
    </div>
  );
}

// ───────────────────────── 유틸 ─────────────────────────

/** datetime-local 값(로컬 시각) → ISO. 미래가 아니면 null. */
function toIso(localValue: string): string | null {
  if (!localValue) return null;
  const t = new Date(localValue).getTime();
  if (!Number.isFinite(t) || t <= Date.now()) return null;
  return new Date(t).toISOString();
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return "";
  return d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

function initialNotice(notice: string | null): string | null {
  if (!notice) return null;
  if (notice === "connected") return "Threads 계정을 연결했어요. 이제 초안을 만들어 발행해 보세요.";
  if (notice.startsWith("error:")) {
    const code = notice.slice(6);
    if (code === "denied") return null; // 사용자가 취소 — 조용히
    return "연결에 실패했어요. 다시 시도해 주세요.";
  }
  return null;
}
