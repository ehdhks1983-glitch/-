"use client";

// components/ViewTracker.tsx  [신규 — 성과 리포트 P1]
// 공개 페이지 방문 1회 기록. 같은 탭(세션)에서 새로고침해도 한 번만 센다.
// 유입 경로 분류값만 보내고, 신청 폼이 같은 값을 쓰도록 sessionStorage 에 남긴다.

import { useEffect } from "react";
import { detectSource, sourceStorageKey } from "@/lib/analytics/source";

export default function ViewTracker({ projectId }: { projectId: string }) {
  useEffect(() => {
    try {
      const key = sourceStorageKey(projectId);
      if (sessionStorage.getItem(key)) return;
      const source = detectSource(document.referrer, location.search, navigator.userAgent, location.hostname);
      sessionStorage.setItem(key, source);
      void fetch("/api/views", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ projectId, source }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      // sessionStorage 불가 환경(시크릿 모드 등)은 집계를 건너뛴다
    }
  }, [projectId]);
  return null;
}
