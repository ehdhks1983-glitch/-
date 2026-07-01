// components/site/Wordmark.tsx — 브랜드 워드마크(다크 서피스용).
import Link from "next/link";
import { BRAND } from "@/lib/brand";

export default function Wordmark({ className = "" }: { className?: string }) {
  return (
    <Link href="/" className={`font-sans font-black tracking-tight ${className}`}>
      <span className="text-paper">{BRAND.nameLead}</span>
      <span className="text-film">{BRAND.nameAccent}</span>
    </Link>
  );
}
