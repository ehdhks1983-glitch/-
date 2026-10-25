"use client";

// components/ForeignPackagePanel.tsx  [신규 — P2 외국인 손님 패키지]
// 편집 화면 패널: 매장 정보 입력 + 외국인 손님용 번역(영·일·중 간체/번체) 만들기 + 미리보기 언어 전환 +
// 구글 비즈니스 프로필에 붙여넣을 언어별 소개문·해시태그 복사.

import { useState } from "react";
import { FOREIGN_LANGS, LANG_NAMES, type ForeignLang, type PageLang, type PlaceInfo, type Translations } from "@/lib/i18n/langs";

const FIELDS: { key: keyof PlaceInfo; label: string; placeholder: string; maxLength: number }[] = [
  { key: "name", label: "상호", placeholder: "예) 서면 수제청 카페", maxLength: 60 },
  { key: "address", label: "주소", placeholder: "예) 부산 부산진구 서면로 00", maxLength: 120 },
  { key: "phone", label: "전화", placeholder: "예) 051-000-0000", maxLength: 30 },
  { key: "hours", label: "영업시간", placeholder: "예) 매일 10:00~21:00 (월 휴무)", maxLength: 120 },
];

export default function ForeignPackagePanel({
  place,
  onPlaceChange,
  serviceName,
  translations,
  translating,
  onTranslate,
  previewLang,
  onPreviewLangChange,
  sourceLang,
}: {
  place: PlaceInfo;
  onPlaceChange: (v: PlaceInfo) => void;
  serviceName: string;
  translations: Translations;
  translating: boolean;
  onTranslate: (langs: ForeignLang[]) => void;
  previewLang: PageLang;
  onPreviewLangChange: (v: PageLang) => void;
  sourceLang: PageLang;
}) {
  const [langs, setLangs] = useState<ForeignLang[]>([...FOREIGN_LANGS]);
  const [copied, setCopied] = useState("");
  const done = FOREIGN_LANGS.filter((l) => translations[l]);

  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      // clipboard 불가 환경 무시
    }
  }

  return (
    <details className="mb-4 rounded-xl border border-slate-200 bg-white p-4 text-sm open:shadow-sm">
      <summary className="cursor-pointer font-medium text-slate-700">
        🌏 매장 정보 · 외국인 손님용 번역 {done.length > 0 && <span className="text-slate-400">({done.map((l) => LANG_NAMES[l]).join(", ")})</span>}
      </summary>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <label key={f.key} className="block">
            <span className="mb-1 block text-slate-600">{f.label}</span>
            <input
              value={place[f.key] ?? ""}
              onChange={(e) => onPlaceChange({ ...place, [f.key]: e.target.value })}
              placeholder={f.key === "name" && serviceName ? serviceName : f.placeholder}
              maxLength={f.maxLength}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-indigo-400"
            />
          </label>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-400">
        주소를 넣으면 공개 페이지에 ‘매장 안내’와 네이버·구글 지도 링크가 붙고, 검색엔진·AI가 읽는 매장 정보(구조화 데이터)도 함께 나가요.
      </p>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <p className="font-medium text-slate-700">외국인 손님용 번역</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          {FOREIGN_LANGS.map((l) => (
            <label key={l} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={langs.includes(l)}
                onChange={(e) => setLangs((cur) => (e.target.checked ? [...cur, l] : cur.filter((x) => x !== l)))}
              />
              {LANG_NAMES[l]}
            </label>
          ))}
          <button
            onClick={() => onTranslate(langs)}
            disabled={translating || langs.length === 0}
            className="rounded-lg bg-slate-900 px-3 py-1.5 font-semibold text-white transition hover:bg-slate-700 disabled:opacity-40"
          >
            {translating ? "번역 중…" : done.length ? "다시 번역" : "번역 만들기"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          원문과 같은 뜻으로만 옮기고 새 주장·효능·후기를 더하지 않도록 지시해요. 게시 승인은 원문(한국어) 검사 결과 기준이에요. 문구를 다시 생성하면 번역은 지워져요.
        </p>

        {done.length > 0 && (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="text-slate-500">미리보기 언어</span>
              {[sourceLang, ...done].map((l) => (
                <button
                  key={l}
                  onClick={() => onPreviewLangChange(l)}
                  className={
                    "rounded-full border px-3 py-1 transition " +
                    (previewLang === l ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:border-slate-400")
                  }
                >
                  {LANG_NAMES[l]}
                </button>
              ))}
            </div>
            <div className="mt-4 space-y-3">
              {done.map((l) => {
                const t = translations[l]!;
                const tags = t.hashtags.join(" ");
                return (
                  <div key={l} className="rounded-lg bg-slate-50 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{LANG_NAMES[l]} · 구글 비즈니스 프로필 소개문</span>
                      <button onClick={() => copy(t.summary, `s-${l}`)} className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs">
                        {copied === `s-${l}` ? "복사됨!" : "복사"}
                      </button>
                    </div>
                    <p className="mt-1 whitespace-pre-line text-slate-600">{t.summary || "—"}</p>
                    {tags && (
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <span className="break-all text-slate-500">{tags}</span>
                        <button onClick={() => copy(tags, `h-${l}`)} className="shrink-0 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs">
                          {copied === `h-${l}` ? "복사됨!" : "해시태그 복사"}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </details>
  );
}
