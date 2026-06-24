"use client";

// components/shell/Topbar.tsx — 상단바 (스펙 §10): 곰대리 로고 · 멀티발행 · 크레딧 잔액 · 계정.

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowser } from "@/lib/db/supabase";
import CreditBadge from "./CreditBadge";

export default function Topbar({ email, configured }: { email: string | null; configured: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function logout() {
    setLoading(true);
    try {
      await createSupabaseBrowser().auth.signOut();
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-stone-200 bg-white/90 backdrop-blur">
      <div className="flex h-14 items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/workspace" className="flex items-center gap-2 font-extrabold tracking-tight">
          <span aria-hidden className="text-xl">🐻</span>
          <span>곰대리</span>
          <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-800">
            멀티발행
          </span>
        </Link>

        <div className="flex items-center gap-3">
          <CreditBadge />

          {configured && email ? (
            <div className="relative">
              <button
                onClick={() => setOpen((v) => !v)}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-800 text-sm font-bold text-white"
                aria-haspopup="menu"
                aria-expanded={open}
                title={email}
              >
                {email.slice(0, 1).toUpperCase()}
              </button>
              {open && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} aria-hidden />
                  <div className="absolute right-0 z-20 mt-2 w-56 rounded-xl border border-stone-200 bg-white p-2 shadow-lg">
                    <p className="truncate px-3 py-2 text-xs text-stone-500">{email}</p>
                    <button
                      onClick={logout}
                      disabled={loading}
                      className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-50"
                    >
                      {loading ? "로그아웃 중…" : "로그아웃"}
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <span className="rounded-full border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-500">
              체험 모드
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
