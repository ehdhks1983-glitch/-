"use client";

// components/ShareLinks.tsx  [신규 — 성과 리포트 P1]
// 채널별 공유 링크(utm_source 부착). 채널마다 다른 링크를 쓰면 유입 경로가 정확히 잡힌다
// (카카오톡·인스타 인앱 브라우저는 referrer 가 비는 경우가 많음).

import { useState } from "react";
import { SOURCE_LABELS, type TrafficSource } from "@/lib/analytics/source";

const CHANNELS: TrafficSource[] = ["naver", "instagram", "kakao", "threads", "youtube"];

export default function ShareLinks({ slug }: { slug: string }) {
  const [copied, setCopied] = useState<TrafficSource | null>(null);

  async function copy(source: TrafficSource) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/s/${slug}?utm_source=${source}`);
      setCopied(source);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      // clipboard 불가 환경 무시
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      {CHANNELS.map((source) => (
        <button
          key={source}
          onClick={() => copy(source)}
          className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm transition hover:border-indigo-300"
        >
          {copied === source ? "복사됨!" : `${SOURCE_LABELS[source]}용 링크 복사`}
        </button>
      ))}
    </div>
  );
}
