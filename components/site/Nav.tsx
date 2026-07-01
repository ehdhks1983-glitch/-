// components/site/Nav.tsx — 상단 내비게이션(서버 컴포넌트).
import Link from "next/link";
import Wordmark from "./Wordmark";

const LINKS = [
  { href: "/#how", label: "작동 방식" },
  { href: "/#packages", label: "요금" },
  { href: "/#legal", label: "공정위 합법" },
  { href: "/apply/creator", label: "크리에이터" },
];

export default function Nav() {
  return (
    <header className="sticky top-0 z-30 border-b border-stone-200/70 bg-stone-50/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
        <Wordmark />
        <nav className="hidden items-center gap-7 text-sm text-stone-600 md:flex">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="transition hover:text-stone-900">
              {l.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/apply/host"
          className="rounded-full bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800"
        >
          숙소 신청
        </Link>
      </div>
    </header>
  );
}
