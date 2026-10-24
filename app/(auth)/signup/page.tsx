"use client";

// app/(auth)/signup/page.tsx  [신규]
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createSupabaseBrowser, isSupabaseConfigured } from "@/lib/db/supabase";
import { AuthShell, Field } from "@/components/auth";
import { AI_NOTICE_VERSION, AI_PRE_NOTICE } from "@/lib/compliance/notice";

export default function SignupPage() {
  const router = useRouter();
  const configured = isSupabaseConfigured();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [aiNoticeAck, setAiNoticeAck] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!configured) {
      setError("회원가입이 아직 설정되지 않았어요. (Supabase 환경변수 필요)");
      return;
    }
    if (password.length < 6) {
      setError("비밀번호는 6자 이상이어야 해요.");
      return;
    }
    if (!aiNoticeAck) {
      setError("생성형 AI 서비스 안내를 확인해 주세요.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    const supabase = createSupabaseBrowser();
    // AI 기본법 사전고지 동의 기록(버전·시각) — 사용자 메타데이터에 남긴다.
    const { data, error: err } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: { data: { ai_notice_version: AI_NOTICE_VERSION, ai_notice_ack_at: new Date().toISOString() } },
    });
    setLoading(false);
    if (err) {
      setError(/registered|exists/i.test(err.message) ? "이미 가입된 이메일이에요." : "회원가입에 실패했어요. 다시 시도해 주세요.");
      return;
    }
    if (data.session) {
      router.push("/dashboard");
      router.refresh();
    } else {
      setMessage("확인 메일을 보냈어요. 메일의 링크를 눌러 가입을 완료해 주세요.");
    }
  }

  return (
    <AuthShell title="회원가입" subtitle="만든 페이지를 저장하고 신청자를 받아보세요.">
      {message ? (
        <p className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="이메일" type="email" value={email} onChange={setEmail} autoComplete="email" />
          <Field
            label="비밀번호 (6자 이상)"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
          />
          <div className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">
            <p>{AI_PRE_NOTICE}</p>
            <label className="mt-2 flex items-start gap-2 font-medium text-slate-700">
              <input
                type="checkbox"
                checked={aiNoticeAck}
                onChange={(e) => setAiNoticeAck(e.target.checked)}
                className="mt-0.5"
              />
              <span>위 내용을 확인했습니다. (필수)</span>
            </label>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "가입 중…" : "회원가입"}
          </button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-slate-500">
        이미 계정이 있으신가요?{" "}
        <Link href="/login" className="font-medium text-indigo-600 hover:underline">
          로그인
        </Link>
      </p>
    </AuthShell>
  );
}
