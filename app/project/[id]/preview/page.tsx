"use client";

// app/project/[id]/preview/page.tsx  [신규]
// 전체화면 미리보기. project 페이지가 sessionStorage 에 저장한 결과를 읽어 렌더한다.
// (Phase 3에서 Supabase 조회로 교체 예정)

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import TemplateRenderer from "@/components/templates/TemplateRenderer";
import type { BizInfo, SectionCopy, TemplateId } from "@/lib/ai/types";

interface Saved {
  biz: BizInfo;
  template: TemplateId;
  copy: SectionCopy;
}

type ViewState = { status: "loading" | "ready" | "empty"; data: Saved | null };

export default function PreviewPage() {
  const params = useParams();
  const projectId = String(params?.id ?? "new");
  const [view, setView] = useState<ViewState>({ status: "loading", data: null });

  useEffect(() => {
    // sessionStorage 는 클라이언트 전용 → 마운트 후 1회 읽어 상태에 주입(SSR 불일치 방지).
    let next: ViewState;
    try {
      const raw = sessionStorage.getItem(`promptsite:project:${projectId}`);
      next = raw
        ? { status: "ready", data: JSON.parse(raw) as Saved }
        : { status: "empty", data: null };
    } catch {
      next = { status: "empty", data: null };
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 클라이언트 전용 저장소를 마운트 후 읽는 정당한 1회 주입
    setView(next);
  }, [projectId]);

  if (view.status === "loading") {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">불러오는 중…</div>;
  }

  const data = view.data;
  if (view.status === "empty" || !data || !data.copy) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 px-6 text-center">
        <p className="text-slate-600">미리볼 내용이 없어요. 먼저 페이지를 만들어 주세요.</p>
        <Link
          href={`/project/${projectId}`}
          className="rounded-full bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
        >
          만들러 가기
        </Link>
      </div>
    );
  }

  return (
    <div className="relative">
      <Link
        href={`/project/${projectId}`}
        className="fixed right-4 top-4 z-50 rounded-full bg-slate-900/80 px-4 py-2 text-sm font-medium text-white backdrop-blur transition hover:bg-slate-900"
      >
        ← 편집으로
      </Link>
      <TemplateRenderer templateId={data.template} copy={data.copy} lang={data.biz?.language ?? "ko"} />
    </div>
  );
}
