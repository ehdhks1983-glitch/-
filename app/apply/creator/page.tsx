// app/apply/creator/page.tsx — 크리에이터 신청.
import type { Metadata } from "next";
import Link from "next/link";
import ApplicationForm from "@/components/ApplicationForm";
import { CREATOR_CONFIG } from "@/lib/applications";
import { Check } from "@/components/site/icons";

export const metadata: Metadata = {
  title: "크리에이터 신청 — 머무는순간",
  description: "여행·숙박·감성 라이프스타일 숏폼 크리에이터 모집. 무료 1박 + 합법 캠페인.",
};

const POINTS = [
  "1박 무료 숙박(현물) 제공 — 감성 스테이에서 직접 촬영",
  "네이버 클립·인스타 릴스 동시 노출 캠페인",
  "퀄리티 검증 크리에이터에게 좋은 캠페인 우선 배정",
];

export default function CreatorApplyPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-14">
      <Link href="/" className="text-sm text-stone-500 hover:text-stone-800">
        ← 홈으로
      </Link>
      <h1 className="mt-4 text-3xl font-bold tracking-tight">{CREATOR_CONFIG.title}</h1>
      <p className="mt-3 leading-7 text-stone-600">{CREATOR_CONFIG.subtitle}</p>

      <ul className="mt-6 space-y-2">
        {POINTS.map((p) => (
          <li key={p} className="flex items-start gap-2 text-sm text-stone-700">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
            <span>{p}</span>
          </li>
        ))}
      </ul>

      <div className="mt-9 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <ApplicationForm kind="creator" />
      </div>

      <p className="mt-6 text-center text-sm text-stone-500">
        숙소를 운영하시나요?{" "}
        <Link href="/apply/host" className="font-medium text-teal-700 hover:underline">
          숙소 캠페인 신청
        </Link>
      </p>
    </div>
  );
}
