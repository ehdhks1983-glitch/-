// components/site/icons.tsx — 가벼운 인라인 SVG 아이콘 모음(currentColor 기반).

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
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M8 5v14l11-7z" />
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

export function MapPin({ className = "h-4 w-4" }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M12 21s-7-6-7-11a7 7 0 0114 0c0 5-7 11-7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

/** 원형 "실제 체크인 인증" 스탬프(세이지 배경 + 체크). 시그니처 요소. */
export function CheckinStamp({ className = "h-16 w-16" }: P) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-full border border-white/30 bg-sage/95 text-center text-on-orange shadow-lg ${className}`}
      aria-label="실제 체크인 인증"
    >
      <Check className="h-5 w-5 text-ink" />
      <span className="mt-0.5 font-mono text-[8px] font-bold leading-tight text-ink">실제 체크인<br />인증</span>
    </div>
  );
}
