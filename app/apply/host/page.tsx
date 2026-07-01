// app/apply/host/page.tsx — 숙소(광고주) 신청.
import type { Metadata } from "next";
import Link from "next/link";
import ApplicationForm from "@/components/ApplicationForm";
import { HOST_CONFIG } from "@/lib/applications";
import { Check } from "@/components/site/icons";

export const metadata: Metadata = {
  title: "숙소 캠페인 신청 — 머무는순간",
  description: "감성 스테이·독채 펜션 운영자를 위한 숏폼 체험단 캠페인 신청.",
};

const POINTS = [
  "비주얼 심사를 통과한 검증된 크리에이터만 매칭",
  "실제 1박 체험 후 촬영 — 가짜 후기 0건",
  "공정위 표기 100% 적용, 광고주 리스크 0",
];

export default function HostApplyPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-14">
      <Link href="/" className="text-sm text-stone-500 hover:text-stone-800">
        ← 홈으로
      </Link>
      <h1 className="mt-4 text-3xl font-bold tracking-tight">{HOST_CONFIG.title}</h1>
      <p className="mt-3 leading-7 text-stone-600">{HOST_CONFIG.subtitle}</p>

      <ul className="mt-6 space-y-2">
        {POINTS.map((p) => (
          <li key={p} className="flex items-start gap-2 text-sm text-stone-700">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
            <span>{p}</span>
          </li>
        ))}
      </ul>

      <div className="mt-9 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <ApplicationForm kind="host" />
      </div>

      <p className="mt-6 text-center text-sm text-stone-500">
        크리에이터로 참여하고 싶으신가요?{" "}
        <Link href="/apply/creator" className="font-medium text-teal-700 hover:underline">
          크리에이터 신청
        </Link>
      </p>
    </div>
  );
}
