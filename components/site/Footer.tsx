// components/site/Footer.tsx — 다크 푸터 + 사업자정보/법적 표기 placeholder.
import Link from "next/link";
import { BRAND } from "@/lib/brand";

// 운영 시 실제 값으로 교체할 사업자정보(전자상거래법 표기 의무 항목).
const BIZ = [
  ["상호", "(주) 머무는순간 · placeholder"],
  ["대표자", "OOO"],
  ["사업자등록번호", "000-00-00000"],
  ["통신판매업신고번호", "제0000-지역-0000호"],
  ["주소", "OO시 OO구 OO로 00, 0층"],
  ["연락처", BRAND.email],
];

export default function Footer() {
  return (
    <footer className="border-t border-line bg-ink">
      <div className="mx-auto max-w-6xl px-5 py-14">
        <div className="flex flex-col gap-10 sm:flex-row sm:justify-between">
          <div className="max-w-sm">
            <p className="font-sans text-lg font-black tracking-tight">
              <span className="text-paper">{BRAND.nameLead}</span>
              <span className="text-film">{BRAND.nameAccent}</span>
            </p>
            <p className="mt-3 font-serif text-sm leading-6 text-paper-dim">{BRAND.tagline}</p>
            <p className="mt-3 font-mono text-xs text-muted">{BRAND.defaultRegionNote}</p>
          </div>
          <div className="grid grid-cols-2 gap-8 text-sm">
            <div>
              <p className="font-mono text-xs uppercase tracking-wider text-muted">신청</p>
              <ul className="mt-3 space-y-2 text-paper/80">
                <li><Link href="/apply/host" className="hover:text-film">무료로 캠페인 만들기</Link></li>
                <li><Link href="/apply/creator" className="hover:text-film">크리에이터 지원</Link></li>
              </ul>
            </div>
            <div>
              <p className="font-mono text-xs uppercase tracking-wider text-muted">안내</p>
              <ul className="mt-3 space-y-2 text-paper/80">
                <li><Link href="/#faq" className="hover:text-film">자주 묻는 질문</Link></li>
                <li><span className="text-muted">이용약관 · 개인정보처리방침 (준비 중)</span></li>
              </ul>
            </div>
          </div>
        </div>

        {/* 사업자정보 */}
        <dl className="mt-10 grid gap-x-8 gap-y-1.5 border-t border-line pt-6 font-mono text-xs text-muted sm:grid-cols-2">
          {BIZ.map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <dt className="shrink-0 text-muted/70">{k}</dt>
              <dd className="text-paper/70">{v}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-6 font-serif text-xs leading-6 text-muted">
          본 서비스의 모든 캠페인은 「표시·광고의 공정화에 관한 법률」과 「추천·보증 등에 관한 표시·광고 심사지침」을
          준수하며, 모든 콘텐츠 제목 또는 본문 첫 줄에 “광고/협찬”을 표기합니다. (표기 예시: “광고 · OO스테이 협찬을 받아 실제 1박 체험 후 작성했습니다.”)
        </p>
        <p className="mt-3 font-mono text-xs text-muted/70">© {BRAND.name}. All rights reserved.</p>
      </div>
    </footer>
  );
}
