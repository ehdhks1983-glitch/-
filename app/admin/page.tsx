// app/admin/page.tsx — 운영자 신청 목록(서버 컴포넌트).
// 보안: SUPABASE_SERVICE_ROLE_KEY 로만 조회(RLS 우회) + ADMIN_EMAILS 로 접근 제한.

import Link from "next/link";
import { redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/db/supabase";
import { createSupabaseServer, createSupabaseAdmin } from "@/lib/db/supabase-server";
import { listApplications, type ApplicationRow } from "@/lib/db/applications";
import { isApplicationKind, type ApplicationKind } from "@/lib/applications";
import LogoutButton from "@/components/LogoutButton";

export const dynamic = "force-dynamic";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50 px-6">
      <div className="max-w-md rounded-2xl border border-stone-200 bg-white p-8 text-center">{children}</div>
    </div>
  );
}

function adminEmails(): string[] {
  return (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

const STATUS_STYLE: Record<ApplicationRow["status"], string> = {
  new: "bg-teal-100 text-teal-800",
  reviewing: "bg-amber-100 text-amber-800",
  accepted: "bg-emerald-100 text-emerald-800",
  rejected: "bg-stone-200 text-stone-600",
};

export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ kind?: string }>;
}) {
  if (!isSupabaseConfigured()) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">설정이 필요해요</h1>
        <p className="mt-2 text-stone-600">
          Supabase 환경변수를 설정하면 신청 접수와 운영자 화면을 쓸 수 있어요.
        </p>
        <Link href="/" className="mt-6 inline-block rounded-full bg-teal-700 px-6 py-2.5 text-sm font-semibold text-white">
          홈으로
        </Link>
      </Centered>
    );
  }

  const supabase = await createSupabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const allowed = adminEmails();
  const email = (user.email ?? "").toLowerCase();
  if (allowed.length > 0 && !allowed.includes(email)) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">접근 권한이 없어요</h1>
        <p className="mt-2 text-stone-600">
          이 계정({email})은 운영자로 등록되어 있지 않습니다. ADMIN_EMAILS 환경변수를 확인해 주세요.
        </p>
        <div className="mt-6">
          <LogoutButton />
        </div>
      </Centered>
    );
  }

  const admin = createSupabaseAdmin();
  if (!admin) {
    return (
      <Centered>
        <h1 className="text-xl font-bold">관리자 키가 필요해요</h1>
        <p className="mt-2 text-stone-600">
          신청 목록 조회에는 <code className="rounded bg-stone-100 px-1">SUPABASE_SERVICE_ROLE_KEY</code> 가
          필요합니다(서버 전용). Vercel 환경변수에 추가해 주세요.
        </p>
        <div className="mt-6">
          <LogoutButton />
        </div>
      </Centered>
    );
  }

  const sp = await searchParams;
  const filter: ApplicationKind | undefined = isApplicationKind(sp.kind) ? sp.kind : undefined;
  const rows = await listApplications(admin, filter);
  const hostCount = filter ? undefined : rows.filter((r) => r.kind === "host").length;
  const creatorCount = filter ? undefined : rows.filter((r) => r.kind === "creator").length;

  const tabs: { key: string; label: string; href: string; active: boolean }[] = [
    { key: "all", label: "전체", href: "/admin", active: !filter },
    { key: "host", label: "숙소", href: "/admin?kind=host", active: filter === "host" },
    { key: "creator", label: "크리에이터", href: "/admin?kind=creator", active: filter === "creator" },
  ];

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <Link href="/" className="font-bold tracking-tight">
            <span className="text-stone-900">머무는</span>
            <span className="text-teal-700">순간</span>
            <span className="ml-2 text-sm font-normal text-stone-400">운영자</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-stone-500 sm:inline">{email}</span>
            <LogoutButton />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">신청 목록</h1>
          <div className="flex gap-1.5">
            {tabs.map((t) => (
              <Link
                key={t.key}
                href={t.href}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  t.active ? "bg-stone-900 text-white" : "border border-stone-200 bg-white text-stone-600 hover:bg-stone-100"
                }`}
              >
                {t.label}
                {t.key === "host" && hostCount !== undefined ? ` ${hostCount}` : ""}
                {t.key === "creator" && creatorCount !== undefined ? ` ${creatorCount}` : ""}
              </Link>
            ))}
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="mt-8 rounded-xl border border-dashed border-stone-300 bg-white px-6 py-12 text-center text-stone-500">
            아직 신청이 없어요.
          </p>
        ) : (
          <ul className="mt-6 space-y-3">
            {rows.map((r) => (
              <li key={r.id} className="rounded-xl border border-stone-200 bg-white p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      r.kind === "host" ? "bg-teal-700 text-white" : "bg-stone-800 text-white"
                    }`}
                  >
                    {r.kind === "host" ? "숙소" : "크리에이터"}
                  </span>
                  <span className="font-semibold">{r.name || "(이름 없음)"}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[r.status]}`}>
                    {r.status}
                  </span>
                  <span className="ml-auto text-xs text-stone-400">
                    {new Date(r.created_at).toLocaleString("ko-KR")}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-stone-600">
                  <a href={`mailto:${r.email}`} className="text-teal-700 hover:underline">
                    {r.email}
                  </a>
                  {r.phone && <span>{r.phone}</span>}
                  {r.region && <span>{r.region}</span>}
                </div>
                <PayloadGrid payload={r.payload} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}

/** payload(추가 필드)를 키-값으로 표시. 이미 윗줄에 나온 기본 필드는 건너뛴다. */
function PayloadGrid({ payload }: { payload: Record<string, unknown> }) {
  const SKIP = new Set(["name", "advertiser_name", "email", "phone", "region", "stay_region", "stay_name"]);
  const entries = Object.entries(payload).filter(([k, v]) => !SKIP.has(k) && typeof v === "string" && v);
  // 숙소명은 별도로 먼저 보여준다.
  const stayName = typeof payload.stay_name === "string" ? payload.stay_name : "";
  if (!stayName && entries.length === 0) return null;
  return (
    <dl className="mt-3 grid gap-x-6 gap-y-1.5 border-t border-stone-100 pt-3 text-sm sm:grid-cols-2">
      {stayName && (
        <div className="flex gap-2 sm:col-span-2">
          <dt className="shrink-0 font-medium text-stone-500">숙소명</dt>
          <dd className="text-stone-800">{stayName}</dd>
        </div>
      )}
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <dt className="shrink-0 font-medium text-stone-500">{k}</dt>
          <dd className="break-all text-stone-800">{v as string}</dd>
        </div>
      ))}
    </dl>
  );
}
