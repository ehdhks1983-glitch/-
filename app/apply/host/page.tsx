// app/apply/host/page.tsx — 광고주(스테이 사장님) 신청.
import type { Metadata } from "next";
import Link from "next/link";
import ApplicationForm from "@/components/ApplicationForm";
import { HOST_CONFIG } from "@/lib/applications";
import { Check } from "@/components/site/icons";

export const metadata: Metadata = {
  title: "무료로 캠페인 만들기 — 머무는순간",
  description: "감성 독채·풀빌라 사장님을 위한 숏폼 체험단 캠페인 신청. 공정위 100% 합법·실제 1박 인증.",
};

const POINTS = [
  "비주얼 심사를 통과한 검증된 크리에이터만 매칭",
  "실제 1박 체험 후 촬영 — 가짜 후기 0건",
  "공정위 표기 100% 적용, 광고주 리스크 0",
];

export default function HostApplyPage() {
  return (
    <div className="mx-auto max-w-2xl px-5 py-14">
      <Link href="/" className="font-mono text-xs uppercase tracking-wider text-muted hover:text-paper">
        ← 홈으로
      </Link>
      <h1 className="headline mt-4 font-sans text-4xl text-paper">{HOST_CONFIG.title}</h1>
      <p className="mt-3 font-serif leading-7 text-paper-dim">{HOST_CONFIG.subtitle}</p>

      <ul className="mt-6 space-y-2">
        {POINTS.map((p) => (
          <li key={p} className="flex items-start gap-2 font-serif text-sm text-paper-dim">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
            <span>{p}</span>
          </li>
        ))}
      </ul>

      <div className="mt-9 rounded-2xl border border-line bg-paper p-6 text-ink sm:p-8">
        <ApplicationForm kind="host" />
      </div>

      <p className="mt-6 text-center font-serif text-sm text-muted">
        크리에이터로 참여하고 싶으신가요?{" "}
        <Link href="/apply/creator" className="font-semibold text-film hover:underline">
          크리에이터 지원
        </Link>
      </p>
    </div>
  );
}
