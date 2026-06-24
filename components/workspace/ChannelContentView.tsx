"use client";

// components/workspace/ChannelContentView.tsx — 채널별 결과 렌더링.
// content는 jsonb(unknown) → 채널별 타입으로 캐스팅. 본문은 마크다운 원문을 그대로(복사 친화).

import type {
  BlogContent,
  CafeContent,
  Channel,
  InstagramContent,
  ShortsContent,
  ThreadsContent,
} from "@/lib/multipublish/types";

function Tags({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((t, i) => (
        <span key={i} className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-stone-600">
          #{t}
        </span>
      ))}
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-stone-400">{title}</h4>
      {children}
    </div>
  );
}

const pre = "whitespace-pre-wrap break-words text-sm leading-relaxed text-stone-800";

export default function ChannelContentView({ channel, content }: { channel: Channel; content: unknown }) {
  if (!content || typeof content !== "object") {
    return <p className="text-sm text-stone-400">내용이 없어요.</p>;
  }

  switch (channel) {
    case "blog": {
      const c = content as BlogContent;
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold">{c.title}</h3>
          {c.meta_description && <p className="text-sm text-stone-500">{c.meta_description}</p>}
          <Block title="본문">
            <div className={pre}>{c.body_markdown}</div>
          </Block>
          <Block title="핵심 태그 (10개)">
            <Tags items={c.tags ?? []} />
          </Block>
          {c.thumbnail_guide && (
            <Block title="썸네일 가이드">
              <p className="text-sm text-stone-600">{c.thumbnail_guide}</p>
            </Block>
          )}
        </div>
      );
    }
    case "threads": {
      const c = content as ThreadsContent;
      return (
        <div className="space-y-3">
          {(c.posts ?? []).map((p, i) => (
            <div key={i} className="rounded-xl border border-stone-200 p-3">
              <div className="mb-1 text-xs text-stone-400">{i + 1} / {(c.posts ?? []).length}</div>
              <div className={pre}>{p}</div>
            </div>
          ))}
          {c.hashtags?.length ? <Tags items={c.hashtags} /> : null}
        </div>
      );
    }
    case "instagram": {
      const c = content as InstagramContent;
      return (
        <div className="space-y-4">
          <Block title="캡션">
            <div className={pre}>{c.caption}</div>
          </Block>
          <Block title={`해시태그 (${(c.hashtags ?? []).length})`}>
            <Tags items={c.hashtags ?? []} />
          </Block>
          <Block title="캐러셀">
            <ol className="space-y-2">
              {(c.carousel ?? []).map((s, i) => (
                <li key={i} className="rounded-lg border border-stone-200 p-2.5">
                  <p className="text-sm font-semibold">{i + 1}. {s.title}</p>
                  {s.body && <p className="mt-0.5 text-sm text-stone-600">{s.body}</p>}
                </li>
              ))}
            </ol>
          </Block>
          {c.image_guide && (
            <Block title="이미지 가이드">
              <p className="text-sm text-stone-600">{c.image_guide}</p>
            </Block>
          )}
        </div>
      );
    }
    case "cafe": {
      const c = content as CafeContent;
      return (
        <div className="space-y-3">
          <h3 className="text-lg font-bold">{c.title}</h3>
          <div className={pre}>{c.body}</div>
          {c.comment_bait && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">💬 {c.comment_bait}</p>}
        </div>
      );
    }
    case "shorts": {
      const c = content as ShortsContent;
      return (
        <div className="space-y-3">
          <p className="text-sm text-stone-500">🎬 약 {c.duration_sec}초</p>
          {(c.scenes ?? []).map((s, i) => (
            <div key={i} className="rounded-xl border border-stone-200 p-3">
              <div className="mb-1 inline-block rounded bg-stone-800 px-2 py-0.5 text-xs font-bold text-white">{s.label}</div>
              <div className={pre}>{s.script}</div>
              {s.subtitle && <p className="mt-1.5 text-sm text-stone-500">📝 자막: {s.subtitle}</p>}
              {s.visual && <p className="text-sm text-stone-500">🎥 화면: {s.visual}</p>}
            </div>
          ))}
        </div>
      );
    }
    default:
      return null;
  }
}
