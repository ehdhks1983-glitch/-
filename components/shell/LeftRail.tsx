"use client";

// components/shell/LeftRail.tsx — 좌측 레일 (스펙 §10 MVP 2개): 새 발행 · 내 발행물.
// (템플릿 갤러리는 P2)

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/workspace", label: "새 발행", icon: "✏️", exact: true },
  { href: "/workspace/library", label: "내 발행물", icon: "📚", exact: false },
];

export default function LeftRail() {
  const pathname = usePathname();

  return (
    <nav className="flex shrink-0 gap-1 border-b border-stone-200 bg-white px-2 py-2 sm:w-52 sm:flex-col sm:border-b-0 sm:border-r sm:py-4">
      {ITEMS.map((it) => {
        const active = it.exact ? pathname === it.href : pathname.startsWith(it.href);
        return (
          <Link
            key={it.href}
            href={it.href}
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
              active ? "bg-emerald-50 text-emerald-800" : "text-stone-600 hover:bg-stone-50"
            }`}
          >
            <span aria-hidden>{it.icon}</span>
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}
