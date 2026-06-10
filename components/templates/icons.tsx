// components/templates/icons.tsx  [신규]
// 기능 카드용 인라인 SVG 아이콘. 인덱스로 결정적으로 순환해 외부 에셋 없이 시각 다양성 확보.

const PATHS = [
  // bolt
  "M13 2 4.5 13.5h5L11 22l8.5-11.5h-5L13 2Z",
  // shield-check
  "M12 2 4 5.5v5.6c0 4.6 3.2 8.9 8 9.9 4.8-1 8-5.3 8-9.9V5.5L12 2Zm-1.2 13.6-3.1-3.1 1.4-1.4 1.7 1.7 4.1-4.1 1.4 1.4-5.5 5.5Z",
  // clock
  "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5h-2v6l5 3 1-1.7-4-2.3V7Z",
  // chat
  "M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 1-2Zm3 5v2h10V8H7Zm0 4v2h7v-2H7Z",
  // chart
  "M4 20V10h3v10H4Zm6.5 0V4h3v16h-3ZM17 20v-7h3v7h-3Z",
  // target
  "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12Zm0 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
  // sparkles
  "M9 2 7.5 7.5 2 9l5.5 1.5L9 16l1.5-5.5L16 9l-5.5-1.5L9 2Zm9 8-1 3.5L13.5 14l3.5 1 1 3.5 1-3.5 3.5-1-3.5-.5-1-3.5Z",
  // layers
  "m12 2 10 5.5L12 13 2 7.5 12 2Zm-7.6 8.6L12 14.9l7.6-4.3L22 12l-10 5.5L2 12l2.4-1.4Zm0 4.5L12 19.4l7.6-4.3L22 16.5 12 22 2 16.5l2.4-1.4Z",
];

/** i번째 기능 아이콘(순환). className 으로 크기/색 제어. */
export function FeatureIcon({ i, className = "h-5 w-5" }: { i: number; className?: string }) {
  const d = PATHS[i % PATHS.length];
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

/** 체크 아이콘(리스트형 템플릿용). */
export function CheckIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
      <path d="m5 12 5 5 9-10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
