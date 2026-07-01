// components/site/Nav.tsx — sticky 미니멀 헤더(다크).
import Link from "next/link";
import Wordmark from "./Wordmark";

export default function Nav() {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-ink/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <Wordmark className="text-lg" />
        <nav className="hidden items-center gap-7 font-mono text-xs uppercase tracking-wider text-muted md:flex">
          <Link href="/#how" className="transition hover:text-paper">이용 방법</Link>
          <Link href="/#evidence" className="transition hover:text-paper">증거</Link>
          <Link href="/#pricing" className="transition hover:text-paper">가격</Link>
          <Link href="/#faq" className="transition hover:text-paper">FAQ</Link>
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href="/apply/creator"
            className="rounded-full border border-line px-3.5 py-2 text-sm font-semibold text-paper/90 transition hover:border-paper/40"
          >
            크리에이터 지원
          </Link>
          <Link
            href="/#apply"
            className="rounded-full bg-film px-4 py-2 text-sm font-bold text-on-orange transition hover:brightness-110"
          >
            무료로 시작하기
          </Link>
        </div>
      </div>
    </header>
  );
}
