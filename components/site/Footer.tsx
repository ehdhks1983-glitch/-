// components/site/Footer.tsx — 하단 푸터(서버 컴포넌트).
import Link from "next/link";
import { BRAND } from "@/lib/brand";

export default function Footer() {
  return (
    <footer className="border-t border-stone-200 bg-stone-100">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="flex flex-col gap-8 sm:flex-row sm:justify-between">
          <div className="max-w-xs">
            <p className="font-bold tracking-tight">
              <span className="text-stone-900">{BRAND.nameLead}</span>
              <span className="text-teal-700">{BRAND.nameAccent}</span>
            </p>
            <p className="mt-2 text-sm leading-6 text-stone-500">{BRAND.tagline}</p>
            <p className="mt-3 text-xs text-stone-400">{BRAND.defaultRegionNote}</p>
          </div>
          <div className="grid grid-cols-2 gap-8 text-sm">
            <div>
              <p className="font-semibold text-stone-700">신청</p>
              <ul className="mt-3 space-y-2 text-stone-500">
                <li><Link href="/apply/host" className="hover:text-stone-900">숙소 캠페인 신청</Link></li>
                <li><Link href="/apply/creator" className="hover:text-stone-900">크리에이터 합류</Link></li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-stone-700">안내</p>
              <ul className="mt-3 space-y-2 text-stone-500">
                <li><Link href="/#legal" className="hover:text-stone-900">공정위 합법 정책</Link></li>
                <li><a href={`mailto:${BRAND.email}`} className="hover:text-stone-900">{BRAND.email}</a></li>
              </ul>
            </div>
          </div>
        </div>
        <div className="mt-10 border-t border-stone-200 pt-6 text-xs text-stone-400">
          <p>
            모든 캠페인은 표시·광고의 공정화에 관한 법률과 추천·보증 등에 관한 표시·광고 심사지침을
            준수합니다. 모든 콘텐츠 제목 또는 본문 첫 줄에 “광고/협찬”을 표기합니다.
          </p>
          <p className="mt-2">© {BRAND.name}. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
