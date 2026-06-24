"use client";

// components/shell/CreditBadge.tsx — 크레딧(포인트) 잔액 표시 (스펙 §10 상단바).
// /api/wallet 폴링 없이 마운트 시 1회 + 'wallet:refresh' 윈도우 이벤트로 갱신.
// (생성/재생성 후 차감되면 호출부가 dispatchEvent(new Event('wallet:refresh')) 로 갱신)

import { useCallback, useEffect, useState } from "react";

export const WALLET_REFRESH_EVENT = "wallet:refresh";

export default function CreditBadge() {
  const [balance, setBalance] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/wallet", { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as { balance?: number };
      if (typeof data.balance === "number") setBalance(data.balance);
    } catch {
      /* 표시는 보조 정보 — 실패해도 무시 */
    }
  }, []);

  useEffect(() => {
    load();
    const onRefresh = () => load();
    window.addEventListener(WALLET_REFRESH_EVENT, onRefresh);
    return () => window.removeEventListener(WALLET_REFRESH_EVENT, onRefresh);
  }, [load]);

  return (
    <span
      title="크레딧 잔액 (1세트 = 10P)"
      className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-800"
    >
      <span aria-hidden>🪙</span>
      {balance === null ? "—" : `${balance.toLocaleString()} P`}
    </span>
  );
}
