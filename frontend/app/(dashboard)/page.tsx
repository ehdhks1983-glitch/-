"use client";

import { useQuery } from "@tanstack/react-query";
import { AlarmClock, CalendarPlus, KeyRound, MonitorSmartphone } from "lucide-react";
import Link from "next/link";

import { ProductChart } from "@/components/product-chart";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { PLAN_LABELS, formatDateKST } from "@/lib/utils";

export default function DashboardPage() {
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.statsSummary });
  const recent = useQuery({
    queryKey: ["recent-licenses"],
    queryFn: () => api.listLicenses({ page: 1, page_size: 10 }),
  });

  const s = summary.data;
  const cards = [
    { label: "총 활성 키", value: s?.total_active, icon: KeyRound },
    { label: "7일 내 만료", value: s?.expiring_soon, icon: AlarmClock },
    { label: "오늘 발급", value: s?.issued_today, icon: CalendarPlus },
    { label: "활성 HWID", value: s?.active_hwids, icon: MonitorSmartphone },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">대시보드</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <Card key={c.label}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {c.label}
                </CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{c.value ?? "–"}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>최근 발급 키</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>키</TableHead>
                  <TableHead>제품</TableHead>
                  <TableHead>플랜</TableHead>
                  <TableHead>고객</TableHead>
                  <TableHead>만료</TableHead>
                  <TableHead>상태</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.data?.items.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="font-mono">
                      <Link href={`/licenses/${l.id}`} className="hover:underline">
                        {l.key_prefix}…
                      </Link>
                    </TableCell>
                    <TableCell>{l.product_code}</TableCell>
                    <TableCell>{PLAN_LABELS[l.plan_type]}</TableCell>
                    <TableCell>{l.customer_name ?? "-"}</TableCell>
                    <TableCell>{formatDateKST(l.expires_at)}</TableCell>
                    <TableCell>
                      <StatusBadge status={l.status} />
                    </TableCell>
                  </TableRow>
                ))}
                {recent.data?.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      발급된 키가 없습니다.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>제품별 활성 키</CardTitle>
          </CardHeader>
          <CardContent>
            {s ? (
              <ProductChart data={s.by_product} />
            ) : (
              <p className="text-sm text-muted-foreground">로딩 중...</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
