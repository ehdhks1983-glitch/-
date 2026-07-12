"use client";

// app/wordpress/page.tsx  [신규 — 워드프레스 자동 발행]
// 연결 설정: 사이트 주소 + 아이디 + 응용 프로그램 비밀번호 → 테스트 후 저장(localStorage).
// 연결되어 있으면 요약 카드 + 기능 바로가기를 보여준다.

import { useState } from "react";
import Link from "next/link";
import {
  clearWpConnection,
  saveWpConnection,
  useWpConnection,
} from "@/lib/wp/clientStore";

interface TestResponse {
  ok: boolean;
  connection: { url: string; user: string };
  site: { name: string; url: string };
  wpUser: { name: string };
  error?: string;
}

const SHORTCUTS = [
  { href: "/wordpress/categories", icon: "📂", title: "카테고리 관리", desc: "추가·수정·삭제, 글 개수 확인" },
  { href: "/wordpress/write", icon: "✍️", title: "AI 글쓰기", desc: "키워드 하나로 초안 생성 후 발행" },
  { href: "/wordpress/bulk", icon: "⚡", title: "대량 자동화", desc: "키워드 여러 개를 예약 발행으로" },
  { href: "/wordpress/posts", icon: "📋", title: "발행 현황", desc: "발행·예약·임시글 한눈에" },
];

export default function WpConnectPage() {
  const conn = useWpConnection();

  const [url, setUrl] = useState("");
  const [user, setUser] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);

  if (conn === undefined) {
    return <p className="py-20 text-center text-sm text-slate-400">불러오는 중…</p>;
  }

  async function connect() {
    setError("");
    setTesting(true);
    try {
      const res = await fetch("/api/wp/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, user, appPassword }),
      });
      const data = (await res.json().catch(() => ({}))) as TestResponse;
      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "연결에 실패했어요. 입력 정보를 확인해 주세요.");
      }
      saveWpConnection({
        url: data.connection.url,
        user: data.connection.user,
        appPassword: appPassword.trim(),
        siteName: data.site.name,
        userName: data.wpUser.name,
        savedAt: new Date().toISOString(),
      });
      setUrl("");
      setUser("");
      setAppPassword("");
      setEditing(false); // 저장 알림으로 훅이 자동 갱신됨
    } catch (e) {
      setError(e instanceof Error ? e.message : "연결에 실패했어요.");
    } finally {
      setTesting(false);
    }
  }

  function disconnect() {
    if (!window.confirm("연결을 해제할까요? 저장된 접속 정보가 이 브라우저에서 삭제됩니다.")) return;
    clearWpConnection();
  }

  // ── 연결된 상태 ──
  if (conn && !editing) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-emerald-700">
                <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                연결됨
              </p>
              <h1 className="mt-1 text-xl font-bold text-slate-900">{conn.siteName}</h1>
              <p className="mt-1 text-sm text-slate-600">
                {conn.url} · {conn.userName} 계정
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setEditing(true)}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                다시 연결
              </button>
              <button
                onClick={disconnect}
                className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50"
              >
                연결 해제
              </button>
            </div>
          </div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          {SHORTCUTS.map((s) => (
            <Link
              key={s.href}
              href={s.href}
              className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-indigo-300 hover:shadow-sm"
            >
              <div className="text-2xl">{s.icon}</div>
              <h2 className="mt-3 font-semibold text-slate-900 group-hover:text-indigo-700">
                {s.title}
              </h2>
              <p className="mt-1 text-sm text-slate-500">{s.desc}</p>
            </Link>
          ))}
        </section>
      </div>
    );
  }

  // ── 미연결(또는 다시 연결) 폼 ──
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">워드프레스 연결</h1>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        내 워드프레스 사이트를 연결하면 카테고리 관리, AI 글쓰기, 예약 자동 발행을 이 화면에서 할 수
        있어요. 접속 정보는 <strong>이 브라우저에만</strong> 저장되고 서버에는 저장되지 않습니다.
      </p>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-3">
          <div className="space-y-4">
            <div>
              <label htmlFor="wp-url" className="text-sm font-medium text-slate-700">
                사이트 주소
              </label>
              <input
                id="wp-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://myblog.com"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="wp-user" className="text-sm font-medium text-slate-700">
                워드프레스 아이디
              </label>
              <input
                id="wp-user"
                type="text"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                placeholder="admin"
                autoComplete="off"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="wp-pass" className="text-sm font-medium text-slate-700">
                응용 프로그램 비밀번호
              </label>
              <input
                id="wp-pass"
                type="password"
                value={appPassword}
                onChange={(e) => setAppPassword(e.target.value)}
                placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
                autoComplete="off"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
              <p className="mt-1.5 text-xs text-slate-400">
                로그인 비밀번호가 아니라 프로필에서 발급하는 별도 비밀번호예요. →
              </p>
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600">{error}</p>
            )}

            <div className="flex gap-2">
              <button
                onClick={connect}
                disabled={testing || !url.trim() || !user.trim() || !appPassword.trim()}
                className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {testing ? "연결 확인 중…" : "연결 테스트 후 저장"}
              </button>
              {editing && (
                <button
                  onClick={() => {
                    setEditing(false);
                    setError("");
                  }}
                  className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
                >
                  취소
                </button>
              )}
            </div>
          </div>
        </section>

        <aside className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-6 text-sm leading-6 text-slate-700 lg:col-span-2">
          <h2 className="font-semibold text-slate-900">응용 프로그램 비밀번호 발급 방법</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-4">
            <li>
              워드프레스 관리자 → <strong>사용자 → 프로필</strong>
            </li>
            <li>
              아래쪽 <strong>응용 프로그램 비밀번호</strong>에서 이름(예: promptsite) 입력 후{" "}
              <strong>추가</strong>
            </li>
            <li>한 번만 표시되는 24자리 비밀번호를 복사해 왼쪽에 붙여넣기</li>
          </ol>
          <p className="mt-4 text-xs leading-5 text-slate-500">
            · 사이트가 https 여야 해요.
            <br />
            · 워드프레스 5.6 이상이면 기본 지원. 항목이 안 보이면 보안 플러그인에서 REST API /
            응용 프로그램 비밀번호 차단 여부를 확인해 주세요.
            <br />· 연결을 끊고 싶으면 같은 화면에서 비밀번호를 <strong>철회</strong>하면 즉시
            무효화됩니다.
          </p>
          <p className="mt-4 rounded-lg bg-white px-3 py-2.5 text-xs leading-5 text-slate-600">
            🌱 워드프레스 사이트가 아직 없거나 용어가 낯설다면{" "}
            <Link href="/wordpress/guide" className="font-semibold text-indigo-600 hover:underline">
              입문 가이드
            </Link>
            에서 구조와 시작 방법(호스팅→설치→연결)을 먼저 확인하세요.
          </p>
        </aside>
      </div>
    </div>
  );
}
