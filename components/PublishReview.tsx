"use client";

// components/PublishReview.tsx  [신규 — 컴플라이언스 P0]
// 게시 전 확인 창. 금칙어 검사 결과 · 업종 필수 표시 항목 · AI 표시 설정 · 사장님 승인을 한 화면에서 받는다.
// block 이 남아 있으면 게시 버튼을 막고 '다시 생성'을 안내한다. 서버도 같은 검사를 다시 한다.

import { useState } from "react";
import type { Finding } from "@/lib/compliance/check";
import {
  DISCLOSURE_META,
  getIndustry,
  missingDisclosures,
  type Disclosures,
  type IndustryId,
} from "@/lib/compliance/industries";

export default function PublishReview({
  findings,
  industry,
  aiLabel,
  onAiLabelChange,
  disclosures,
  onDisclosuresChange,
  publishing,
  isUpdate,
  error,
  onCancel,
  onConfirm,
  onRegenerate,
}: {
  findings: Finding[];
  industry: IndustryId;
  aiLabel: boolean;
  onAiLabelChange: (v: boolean) => void;
  disclosures: Disclosures;
  onDisclosuresChange: (v: Disclosures) => void;
  publishing: boolean;
  isUpdate: boolean;
  /** 서버가 게시를 거절한 사유(서버 재검사 결과) */
  error?: string;
  onCancel: () => void;
  onConfirm: (opts: { labelOffAck: boolean }) => void;
  onRegenerate: () => void;
}) {
  const [approved, setApproved] = useState(false);
  const [labelOffAck, setLabelOffAck] = useState(false);

  const preset = getIndustry(industry);
  const blocks = findings.filter((f) => f.severity === "block");
  const warns = findings.filter((f) => f.severity === "warn");
  const missing = missingDisclosures(industry, disclosures);
  const canPublish = blocks.length === 0 && missing.length === 0 && approved && (aiLabel || labelOffAck) && !publishing;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-6" role="dialog" aria-modal="true">
      <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-t-2xl bg-white p-6 shadow-xl sm:rounded-2xl">
        <h2 className="text-xl font-bold">게시 전 확인</h2>
        <p className="mt-1 text-sm text-slate-500">
          업종: <span className="font-medium text-slate-700">{preset.name}</span> 기준으로 광고 문구를 검사했어요.
        </p>

        {/* 검사 결과 */}
        <section className="mt-5">
          {findings.length === 0 ? (
            <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              문제 될 만한 표현을 찾지 못했어요. 그래도 사실과 다른 내용이 없는지 한 번 더 확인해 주세요.
            </p>
          ) : (
            <ul className="space-y-2">
              {[...blocks, ...warns].map((f, i) => (
                <li
                  key={`${f.ruleId}-${f.field}-${i}`}
                  className={
                    "rounded-lg border px-4 py-3 text-sm " +
                    (f.severity === "block"
                      ? "border-red-200 bg-red-50 text-red-800"
                      : "border-amber-200 bg-amber-50 text-amber-900")
                  }
                >
                  <p className="font-semibold">
                    {f.severity === "block" ? "게시 불가" : "확인 필요"} · {f.fieldLabel} · “{f.match}”
                  </p>
                  <p className="mt-1">{f.message}</p>
                  <p className="mt-1 text-xs opacity-70">근거: {f.basis}</p>
                </li>
              ))}
            </ul>
          )}
          {blocks.length > 0 && (
            <div className="mt-3 flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <span>‘다시 생성’을 누르면 문제 표현을 빼고 새로 써요.</span>
              <button
                onClick={onRegenerate}
                className="shrink-0 rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-slate-700"
              >
                다시 생성
              </button>
            </div>
          )}
        </section>

        {/* 업종 필수 표시 */}
        {preset.required.length > 0 && (
          <section className="mt-6">
            <h3 className="text-sm font-semibold">필수 표시 항목</h3>
            <p className="mt-1 text-xs text-slate-500">공개 페이지 하단에 그대로 표시돼요.</p>
            <div className="mt-3 space-y-3">
              {preset.required.map((field) => (
                <label key={field} className="block">
                  <span className="mb-1 block text-sm text-slate-700">{DISCLOSURE_META[field].label}</span>
                  <input
                    value={disclosures[field] ?? ""}
                    onChange={(e) => onDisclosuresChange({ ...disclosures, [field]: e.target.value })}
                    placeholder={DISCLOSURE_META[field].placeholder}
                    maxLength={DISCLOSURE_META[field].maxLen}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                  />
                </label>
              ))}
            </div>
          </section>
        )}

        {/* AI 표시 */}
        <section className="mt-6 space-y-3 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={aiLabel} onChange={(e) => onAiLabelChange(e.target.checked)} className="mt-0.5" />
            <span>
              공개 페이지 하단에 ‘생성형 AI로 작성’ 표시하기 <span className="text-slate-400">(권장)</span>
            </span>
          </label>
          {!aiLabel && (
            <label className="ml-6 flex items-start gap-2 text-amber-900">
              <input type="checkbox" checked={labelOffAck} onChange={(e) => setLabelOffAck(e.target.checked)} className="mt-0.5" />
              <span>문구를 직접 검토·수정했고, AI 표시를 끄는 데 따른 책임을 이해합니다.</span>
            </label>
          )}
          <label className="flex items-start gap-2 font-medium">
            <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} className="mt-0.5" />
            <span>페이지 내용을 직접 확인했고, 사실과 다르거나 지어낸 내용(후기·수치·자격)이 없습니다.</span>
          </label>
        </section>

        {error && <p className="mt-5 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium transition hover:bg-slate-50"
          >
            취소
          </button>
          <button
            onClick={() => onConfirm({ labelOffAck })}
            disabled={!canPublish}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-40"
          >
            {publishing ? "게시 중…" : isUpdate ? "승인하고 업데이트" : "승인하고 게시"}
          </button>
        </div>
      </div>
    </div>
  );
}
