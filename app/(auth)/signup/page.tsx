"use client";

// app/(auth)/signup/page.tsx  [신규]
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createSupabaseBrowser, isSupabaseConfigured } from "@/lib/db/supabase";
import { AuthShell, Field } from "@/components/auth";

export default function SignupPage() {
  const router = useRouter();
  const configured = isSupabaseConfigured();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    setLoading(true);
    setError("");
    setMessage("");
    const supabase = createSupabaseBrowser();
    const { data, error: err } = await supabase.auth.signUp({ email: email.trim(), password });
    setLoading(false);
    if (err) {
      setError(/registered|exists/i.test(err.message) ? "이미 가입된 이메일이에요." : "회원가입에 실패했어요. 다시 시도해 주세요.");
      return;
    }
    if (data.session) {
      router.push("/admin");
      router.refresh();
    } else {
      setMessage("확인 메일을 보냈어요. 메일의 링크를 눌러 가입을 완료해 주세요.");
    }
  }

  return (
    <AuthShell title="운영자 회원가입" subtitle="가입 후 신청 목록을 관리하세요. (ADMIN_EMAILS 등록 필요)">
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
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-teal-700 px-4 py-3 font-semibold text-white transition hover:bg-teal-800 disabled:opacity-50"
          >
            {loading ? "가입 중…" : "회원가입"}
          </button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-stone-500">
        이미 계정이 있으신가요?{" "}
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          로그인
        </Link>
      </p>
    </AuthShell>
  );
}
