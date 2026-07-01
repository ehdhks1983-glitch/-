// components/site/Wordmark.tsx — 브랜드 워드마크.
import Link from "next/link";
import { BRAND } from "@/lib/brand";

export default function Wordmark({ className = "" }: { className?: string }) {
  return (
    <Link href="/" className={`font-bold tracking-tight ${className}`}>
      <span className="text-stone-900">{BRAND.nameLead}</span>
      <span className="text-teal-700">{BRAND.nameAccent}</span>
    </Link>
  );
}
