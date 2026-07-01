// components/site/icons.tsx — 가벼운 인라인 SVG 아이콘 모음.
// 단색(currentColor) + stroke 기반. 색은 부모 text-* 클래스로 제어.

type P = { className?: string };
const base = "h-6 w-6";

export function ShieldCheck({ className = base }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M12 3l7 3v5c0 4.4-3 8.5-7 10-4-1.5-7-5.6-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

export function Sparkles({ className = base }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3z" />
      <path d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14z" />
    </svg>
  );
}

export function Curate({ className = base }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M4 21V8a2 2 0 012-2h12a2 2 0 012 2v13" />
      <path d="M4 21h16" />
      <path d="M9 6V3h6v3" />
      <path d="M12 11l1.2 2.5 2.8.4-2 2 .5 2.8L12 19.6 9.5 20.7l.5-2.8-2-2 2.8-.4L12 11z" />
    </svg>
  );
}

export function Play({ className = base }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <rect x="6" y="3" width="12" height="18" rx="2" />
      <path d="M10.5 9l4 3-4 3V9z" />
    </svg>
  );
}

export function Home({ className = base }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M3 11l9-7 9 7" />
      <path d="M5 10v10h14V10" />
      <path d="M10 20v-6h4v6" />
    </svg>
  );
}

export function Check({ className = "h-5 w-5" }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}
