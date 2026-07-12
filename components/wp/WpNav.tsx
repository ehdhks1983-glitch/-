"use client";

// components/wp/WpNav.tsx  [신규 — 워드프레스 자동 발행]
// /wordpress 하위 공통 탭 내비게이션. 현재 경로에 맞춰 활성 탭 표시.

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/wordpress/guide", label: "입문 가이드", exact: false },
  { href: "/wordpress", label: "연결 설정", exact: true },
  { href: "/wordpress/categories", label: "카테고리 관리", exact: false },
  { href: "/wordpress/write", label: "AI 글쓰기", exact: false },
  { href: "/wordpress/bulk", label: "대량 자동화", exact: false },
  { href: "/wordpress/posts", label: "발행 현황", exact: false },
];

export default function WpNav() {
  const pathname = usePathname() ?? "";

  return (
    <nav className="-mb-px flex gap-1 overflow-x-auto" aria-label="워드프레스 자동화 메뉴">
      {TABS.map((tab) => {
        const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition ${
              active
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
