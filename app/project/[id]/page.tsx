"use client";

// app/project/[id]/page.tsx  [신규]
// 핵심 "딸깍" 화면: 프롬프트 입력 → (보완질문) → 생성 → 인라인 미리보기.
// 생성 결과는 sessionStorage 에 저장해 /preview(전체화면)와 공유한다(Phase 3에서 DB로 교체).

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import TemplateRenderer from "@/components/templates/TemplateRenderer";
import { TEMPLATE_META } from "@/lib/ai/renderPage";
import type { BizInfo, SectionCopy, TemplateId } from "@/lib/ai/types";
import type { ClarifyQuestion } from "@/lib/ai/clarifyQuestions";

type Phase = "input" | "clarify" | "preview";

interface GenerateResult {
  stage: "clarify" | "done";
  biz: BizInfo;
  template: TemplateId;
  questions?: ClarifyQuestion[];
  copy?: SectionCopy;
}

const EXAMPLES = [
  "온라인 PT 코칭 랜딩, 30대 직장인, 무료 상담 신청",
  "수제 디저트 정기구독, 사전 예약 받기",
  "소상공인 SNS 마케팅 대행, 무료 진단 신청",
];

function storageKey(id: string) {
  return `promptsite:project:${id}`;
}

export default function ProjectPage() {
  const params = useParams();
  const projectId = String(params?.id ?? "new");

  const [phase, setPhase] = useState<Phase>("input");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [biz, setBiz] = useState<BizInfo | null>(null);
  const [template, setTemplate] = useState<TemplateId>("saas-launch");
  const [questions, setQuestions] = useState<ClarifyQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [copy, setCopy] = useState<SectionCopy | null>(null);

  function persist(next: { biz: BizInfo; template: TemplateId; copy: SectionCopy }) {
    try {
      sessionStorage.setItem(storageKey(projectId), JSON.stringify(next));
    } catch {
      // sessionStorage 불가 환경은 무시(미리보기 인라인은 그대로 동작)
    }
  }

  async function callGenerate(payload: Record<string, unknown>): Promise<GenerateResult> {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = (await res.json().catch(() => ({}))) as GenerateResult & { error?: string };
    if (!res.ok) throw new Error(data?.error || "생성에 실패했어요. 잠시 후 다시 시도해 주세요.");
    return data;
  }

  function applyResult(r: GenerateResult) {
    setBiz(r.biz);
    setTemplate(r.template);
    if (r.stage === "clarify") {
      setQuestions(r.questions ?? []);
      setAnswers({});
      setPhase("clarify");
    } else if (r.copy) {
      setCopy(r.copy);
      persist({ biz: r.biz, template: r.template, copy: r.copy });
      setPhase("preview");
    }
  }

  async function onGenerate() {
    if (!prompt.trim()) {
      setError("무엇을 만들지 한 줄로 적어 주세요.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      applyResult(await callGenerate({ prompt: prompt.trim() }));
    } catch (e) {
      setError(toMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function onSubmitAnswers(skip: boolean) {
    if (!biz) return;
    setError("");
    setLoading(true);
    try {
      const payload = skip
        ? { biz, skipClarify: true }
        : {
            biz,
            answers: questions
              .map((q, i) => ({ question: q.question, answer: (answers[i] ?? "").trim() }))
              .filter((a) => a.answer),
          };
      applyResult(await callGenerate(payload));
    } catch (e) {
      setError(toMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function onRegenerate() {
    if (!biz) return;
    setError("");
    setLoading(true);
    try {
      applyResult(await callGenerate({ biz, skipClarify: true }));
    } catch (e) {
      setError(toMessage(e));
    } finally {
      setLoading(false);
    }
  }

  function switchTemplate(id: TemplateId) {
    setTemplate(id);
    if (biz && copy) persist({ biz, template: id, copy });
  }

  function reset() {
    setPhase("input");
    setBiz(null);
    setCopy(null);
    setQuestions([]);
    setAnswers({});
    setError("");
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <Link href="/" className="font-bold tracking-tight">
            Prompt<span className="text-indigo-600">Site</span>
          </Link>
          {phase === "preview" && (
            <div className="flex items-center gap-2">
              <button
                onClick={onRegenerate}
                disabled={loading}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50 disabled:opacity-50"
              >
                {loading ? "생성 중…" : "다시 생성"}
              </button>
              <Link
                href={`/project/${projectId}/preview`}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50"
              >
                전체화면
              </Link>
              <button
                onClick={reset}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-slate-700"
              >
                처음부터
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">
        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* INPUT */}
        {phase === "input" && (
          <div className="mx-auto max-w-2xl py-10">
            <h1 className="text-center text-3xl font-bold tracking-tight sm:text-4xl">
              한 줄이면, 랜딩페이지 완성
            </h1>
            <p className="mt-3 text-center text-slate-600">
              무엇을 위한 페이지인지 적어 주세요. AI가 카피와 디자인까지 만들어 드립니다.
            </p>

            <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="예) 온라인 PT 코칭 랜딩페이지, 30대 직장인 대상, 무료 상담 신청을 받고 싶어요"
                rows={4}
                maxLength={2000}
                className="w-full resize-none rounded-lg border-0 p-2 text-base outline-none placeholder:text-slate-400"
              />
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs text-slate-400">{prompt.length}/2000</span>
                <button
                  onClick={onGenerate}
                  disabled={loading}
                  className="rounded-full bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50"
                >
                  {loading ? "만드는 중…" : "딸깍, 만들기"}
                </button>
              </div>
            </div>

            <div className="mt-6">
              <p className="mb-2 text-center text-xs font-medium uppercase tracking-wide text-slate-400">
                예시
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setPrompt(ex)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* CLARIFY */}
        {phase === "clarify" && (
          <div className="mx-auto max-w-xl py-8">
            <h2 className="text-2xl font-bold">조금만 더 알려주세요</h2>
            <p className="mt-2 text-slate-600">
              답할수록 카피가 좋아져요. 건너뛰어도 바로 만들 수 있어요.
            </p>

            <div className="mt-8 space-y-6">
              {questions.map((q, i) => (
                <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5">
                  <p className="font-medium">{q.question}</p>
                  {q.options.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {q.options.map((opt) => {
                        const active = answers[i] === opt;
                        return (
                          <button
                            key={opt}
                            onClick={() => setAnswers((a) => ({ ...a, [i]: active ? "" : opt }))}
                            className={
                              "rounded-full border px-4 py-1.5 text-sm transition " +
                              (active
                                ? "border-indigo-600 bg-indigo-600 text-white"
                                : "border-slate-200 hover:border-indigo-300")
                            }
                          >
                            {opt}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <input
                      value={answers[i] ?? ""}
                      onChange={(e) => setAnswers((a) => ({ ...a, [i]: e.target.value }))}
                      placeholder="자유롭게 적어 주세요 (선택)"
                      maxLength={300}
                      className="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                    />
                  )}
                </div>
              ))}
            </div>

            <div className="mt-8 flex gap-3">
              <button
                onClick={() => onSubmitAnswers(false)}
                disabled={loading}
                className="flex-1 rounded-full bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50"
              >
                {loading ? "만드는 중…" : "이대로 만들기"}
              </button>
              <button
                onClick={() => onSubmitAnswers(true)}
                disabled={loading}
                className="rounded-full border border-slate-200 px-6 py-3 text-sm font-medium transition hover:bg-white disabled:opacity-50"
              >
                건너뛰기
              </button>
            </div>
          </div>
        )}

        {/* PREVIEW */}
        {phase === "preview" && copy && (
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-500">템플릿</span>
              {TEMPLATE_META.map((m) => (
                <button
                  key={m.id}
                  onClick={() => switchTemplate(m.id)}
                  title={m.description}
                  className={
                    "rounded-full border px-3 py-1.5 text-sm transition " +
                    (template === m.id
                      ? "border-indigo-600 bg-indigo-600 text-white"
                      : "border-slate-200 bg-white hover:border-indigo-300")
                  }
                >
                  {m.name}
                </button>
              ))}
            </div>

            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <TemplateRenderer templateId={template} copy={copy} lang={biz?.language ?? "ko"} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function toMessage(e: unknown): string {
  return e instanceof Error ? e.message : "문제가 발생했어요. 잠시 후 다시 시도해 주세요.";
}
