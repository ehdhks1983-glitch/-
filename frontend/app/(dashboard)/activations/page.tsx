"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTimeKST } from "@/lib/utils";

export default function ActivationsPage() {
  const [conflictsOnly, setConflictsOnly] = useState(false);
  const activations = useQuery({
    queryKey: ["activations", conflictsOnly],
    queryFn: () => api.listActivations(conflictsOnly),
  });

  const items = activations.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">활성화 현황</h1>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={conflictsOnly}
            onChange={(e) => setConflictsOnly(e.target.checked)}
          />
          충돌만 보기
        </label>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>HWID</TableHead>
                <TableHead>제품</TableHead>
                <TableHead>라이선스</TableHead>
                <TableHead>최근 접속</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>버전</TableHead>
                <TableHead>상태</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((a) => (
                <TableRow key={a.id} className={a.is_conflict ? "bg-amber-50" : ""}>
                  <TableCell className="font-mono text-xs">{a.hwid}</TableCell>
                  <TableCell>{a.product_code}</TableCell>
                  <TableCell className="font-mono">
                    <Link href={`/licenses/${a.license_id}`} className="hover:underline">
                      {a.license_key_prefix}…
                    </Link>
                  </TableCell>
                  <TableCell>{formatDateTimeKST(a.last_seen_at)}</TableCell>
                  <TableCell>{a.ip_address ?? "-"}</TableCell>
                  <TableCell>{a.client_version ?? "-"}</TableCell>
                  <TableCell>
                    {a.is_conflict ? (
                      <Badge variant="warning">충돌</Badge>
                    ) : (
                      <Badge variant="secondary">정상</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    활성화 기록이 없습니다.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
