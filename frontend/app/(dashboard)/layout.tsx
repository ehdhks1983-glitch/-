"use client";

import {
  KeyRound,
  LayoutDashboard,
  LogOut,
  MonitorSmartphone,
  Package,
  Plus,
  ScrollText,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";

const NAV = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/licenses", label: "라이선스 목록", icon: ScrollText },
  { href: "/licenses/new", label: "키 발급", icon: Plus },
  { href: "/products", label: "제품 관리", icon: Package, adminOnly: true },
  { href: "/activations", label: "활성화 현황", icon: MonitorSmartphone },
  { href: "/users", label: "계정 관리", icon: Users, adminOnly: true },
  { href: "/settings", label: "설정", icon: Settings },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { accessToken, user, hydrated, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (hydrated && !accessToken) router.replace("/login");
  }, [hydrated, accessToken, router]);

  if (!hydrated || !accessToken) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        로딩 중...
      </div>
    );
  }

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r bg-card p-4">
        <div className="flex items-center gap-2 px-2 py-3 text-lg font-bold">
          <KeyRound className="h-5 w-5" /> 센텀하이 라이선스
        </div>
        <nav className="mt-4 flex-1 space-y-1">
          {NAV.filter((n) => !n.adminOnly || user?.role === "admin").map((n) => {
            const active = pathname === n.href;
            const Icon = n.icon;
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-secondary"
                )}
              >
                <Icon className="h-4 w-4" /> {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto border-t pt-3">
          <div className="px-2 text-sm font-medium">{user?.name ?? user?.email}</div>
          <div className="px-2 text-xs text-muted-foreground">
            {user?.role === "admin" ? "관리자" : "스탭"}
          </div>
          <button
            onClick={handleLogout}
            className="mt-2 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-secondary"
          >
            <LogOut className="h-4 w-4" /> 로그아웃
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-secondary/20 p-8">{children}</main>
    </div>
  );
}
