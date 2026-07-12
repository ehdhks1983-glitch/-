// components/wp/NotConnected.tsx  [신규 — 워드프레스 자동 발행]
// 접속 정보가 없을 때 각 기능 페이지에 띄우는 안내 카드.

import Link from "next/link";

export default function NotConnected() {
  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-slate-200 bg-white p-10 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-2xl">
        🔌
      </div>
      <h2 className="text-lg font-bold">먼저 워드프레스와 연결해 주세요</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        사이트 주소와 응용 프로그램 비밀번호로 한 번만 연결하면
        <br />
        카테고리 관리부터 자동 발행까지 바로 쓸 수 있어요.
      </p>
      <Link
        href="/wordpress"
        className="mt-6 inline-block rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
      >
        연결하러 가기
      </Link>
      <p className="mt-4 text-xs text-slate-400">
        워드프레스가 처음이라면{" "}
        <Link href="/wordpress/guide" className="font-medium text-indigo-600 hover:underline">
          입문 가이드
        </Link>
        부터 보세요.
      </p>
    </div>
  );
}
