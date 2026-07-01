// components/site/ContactCard.tsx
// 필름 콘택트시트 카드(9:16). 실사진 준비 전 색상블록 + play 아이콘 + 촬영정보 캡션으로 자리만 잡는다.
// 가짜 후기/스톡사진으로 '실제 체험'을 위장하지 않기 위한 정직한 플레이스홀더.

import { Play, MapPin, CheckinStamp } from "./icons";

export interface ContactCardData {
  region: string;
  date: string; // 모노 캡션(촬영 정보 느낌)
  tone: string; // 배경 색상블록 클래스
  stamped?: boolean;
}

export default function ContactCard({
  data,
  className = "",
  tilt = "",
}: {
  data: ContactCardData;
  className?: string;
  tilt?: string;
}) {
  return (
    <figure
      className={`relative aspect-[9/16] overflow-hidden rounded-lg border border-line ${data.tone} ${tilt} ${className}`}
    >
      {/* 상단: 촬영 타임스탬프 + REC */}
      <div className="absolute left-2 top-2 flex items-center gap-1.5 font-mono text-[10px] text-paper/70">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-film" />
        {data.date}
      </div>

      {/* 중앙 play */}
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full border border-paper/25 bg-ink/30 text-paper/80 backdrop-blur-sm">
          <Play className="ml-0.5 h-4 w-4" />
        </span>
      </div>

      {/* 하단: 지역 태그 */}
      <figcaption className="absolute bottom-2 left-2 flex items-center gap-1 rounded bg-ink/40 px-1.5 py-0.5 font-mono text-[10px] text-paper/85 backdrop-blur-sm">
        <MapPin className="h-3 w-3" />
        {data.region}
      </figcaption>

      {/* 인증 스탬프 */}
      {data.stamped && <CheckinStamp className="absolute -bottom-1 -right-1 h-14 w-14 rotate-[-8deg]" />}
    </figure>
  );
}
