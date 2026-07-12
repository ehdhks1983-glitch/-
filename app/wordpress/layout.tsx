// app/wordpress/layout.tsx  [신규 — 워드프레스 자동 발행]
// /wordpress 하위 공통 셸: 헤더(로고 + 탭) + 본문 + 푸터.

import type { Metadata } from "next";
import Link from "next/link";
import WpNav from "@/components/wp/WpNav";

export const metadata: Metadata = {
  title: "워드프레스 자동 발행 — PromptSite",
  description:
    "워드프레스 블로그 자동화: 카테고리 관리, AI 글쓰기, 예약 발행, 대량 자동 등록까지 한 화면에서.",
};

export default function WordpressLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-6">
          <div className="flex items-center justify-between pt-4">
            <div className="flex items-center gap-3">
              <Link href="/" className="font-bold tracking-tight">
                Prompt<span className="text-indigo-600">Site</span>
              </Link>
              <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
                WP 자동 발행
              </span>
            </div>
            <Link href="/" className="text-sm text-slate-500 transition hover:text-slate-800">
              홈으로
            </Link>
          </div>
          <div className="mt-2">
            <WpNav />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>

      <footer className="border-t border-slate-200 bg-white px-6 py-6">
        <div className="mx-auto max-w-6xl text-center text-xs leading-5 text-slate-400">
          접속 정보는 이 브라우저에만 저장되며 서버에 저장되지 않습니다 ·{" "}
          워드프레스 예약 발행은 사이트 방문이 있어야 정시에 처리됩니다(WP-Cron)
        </div>
      </footer>
    </div>
  );
}
