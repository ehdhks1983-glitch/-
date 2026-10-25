// components/PlaceSection.tsx  [신규 — P2 외국인 손님 패키지]
// 공개 페이지 '매장 안내': 주소·전화·영업시간 + 네이버/구글 지도 링크. 정보가 없으면 렌더하지 않는다.
// 훅 없음 → 서버/클라이언트 양쪽에서 렌더 가능.

import type { PageLang, PlaceInfo } from "@/lib/i18n/langs";
import { uiText } from "@/lib/i18n/ui";
import { hasPlace, mapLinks } from "@/lib/i18n/place";

export default function PlaceSection({ place, lang = "ko", hours }: { place: PlaceInfo; lang?: PageLang; hours?: string }) {
  if (!hasPlace(place)) return null;
  const t = uiText(lang).place;
  const links = mapLinks(place);
  const rows = [
    { label: t.address, value: place.address },
    { label: t.phone, value: place.phone },
    { label: t.hours, value: hours || place.hours },
  ].filter((r) => r.value);

  return (
    <section className="border-t border-slate-200 bg-white px-6 py-14">
      <div className="mx-auto max-w-2xl">
        <h2 className="text-center text-2xl font-bold">{t.title}</h2>
        <dl className="mt-8 space-y-3 text-slate-700">
          {rows.map((r) => (
            <div key={r.label} className="flex gap-4">
              <dt className="w-20 shrink-0 text-slate-400">{r.label}</dt>
              <dd className="break-words">
                {r.label === t.phone ? (
                  <a href={`tel:${r.value!.replace(/[^0-9+]/g, "")}`} className="underline underline-offset-2">
                    {r.value}
                  </a>
                ) : (
                  r.value
                )}
              </dd>
            </div>
          ))}
        </dl>
        {links && (
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <a href={links.naver} target="_blank" rel="noopener noreferrer" className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-semibold transition hover:bg-slate-50">
              {t.naverMap} ↗
            </a>
            <a href={links.google} target="_blank" rel="noopener noreferrer" className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-semibold transition hover:bg-slate-50">
              {t.googleMap} ↗
            </a>
          </div>
        )}
      </div>
    </section>
  );
}
