"use client";

// app/(auth)/login/page.tsx  [신규]
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createSupabaseBrowser, isSupabaseConfigured } from "@/lib/db/supabase";
import { AuthShell, Field } from "@/components/auth";

export default function LoginPage() {
  const router = useRouter();
  const configured = isSupabaseConfigured();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!configured) {
      setError("로그인이 아직 설정되지 않았어요. (Supabase 환경변수 필요)");
      return;
    }
    setLoading(true);
    setError("");
    const supabase = createSupabaseBrowser();
    const { error: err } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    setLoading(false);
    if (err) {
      setError("이메일 또는 비밀번호를 확인해 주세요.");
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <AuthShell title="로그인" subtitle="대시보드에서 만든 페이지와 신청자를 관리하세요.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="이메일" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field
          label="비밀번호"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "로그인 중…" : "로그인"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        계정이 없으신가요?{" "}
        <Link href="/signup" className="font-medium text-indigo-600 hover:underline">
          회원가입
        </Link>
      </p>
    </AuthShell>
  );
}
