"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import {
  AUDIT_EVENT_LABELS,
  PLAN_LABELS,
  formatDateKST,
  formatDateTimeKST,
} from "@/lib/utils";

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{children}</span>
    </div>
  );
}

export default function LicenseDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const qc = useQueryClient();
  const [memo, setMemo] = useState<string | null>(null);
  const [extendDays, setExtendDays] = useState("30");
  const [error, setError] = useState<string | null>(null);

  const license = useQuery({
    queryKey: ["license", id],
    queryFn: () => api.getLicense(id),
  });
  const logs = useQuery({
    queryKey: ["license-logs", id],
    queryFn: () => api.licenseLogs(id),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["license", id] });
    qc.invalidateQueries({ queryKey: ["license-logs", id] });
  };
  const onError = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : "작업 실패");

  const revoke = useMutation({
    mutationFn: () => api.revokeLicense(id),
    onSuccess: refresh,
    onError,
  });
  const extend = useMutation({
    mutationFn: () => api.extendLicense(id, Number(extendDays)),
    onSuccess: refresh,
    onError,
  });
  const saveMemo = useMutation({
    mutationFn: () => api.updateMemo(id, memo),
    onSuccess: refresh,
    onError,
  });
  const release = useMutation({
    mutationFn: (activationId: number) => api.releaseHwid(id, activationId),
    onSuccess: refresh,
    onError,
  });

  if (license.isLoading) return <p className="text-muted-foreground">로딩 중...</p>;
  if (license.isError || !license.data)
    return <p className="text-destructive">라이선스를 찾을 수 없습니다.</p>;

  const l = license.data;
  const memoValue = memo ?? l.memo ?? "";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="font-mono text-xl font-bold">{l.key_prefix}…</h1>
        <StatusBadge status={l.status} />
      </div>

      {error && (
        <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>기본 정보</CardTitle>
          </CardHeader>
          <CardContent>
            <InfoRow label="제품">{l.product_code}</InfoRow>
            <InfoRow label="플랜">{PLAN_LABELS[l.plan_type]}</InfoRow>
            <InfoRow label="고객명">{l.customer_name ?? "-"}</InfoRow>
            <InfoRow label="연락처">{l.customer_contact ?? "-"}</InfoRow>
            <InfoRow label="발급일">{formatDateTimeKST(l.issued_at)}</InfoRow>
            <InfoRow label="만료일">{formatDateKST(l.expires_at)}</InfoRow>
            <InfoRow label="HWID 사용/최대">
              {l.hwid_used}/{l.hwid_max}
            </InfoRow>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>액션</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1">
                <Label>연장 일수</Label>
                <Input
                  type="number"
                  min={1}
                  value={extendDays}
                  onChange={(e) => setExtendDays(e.target.value)}
                />
              </div>
              <Button
                variant="outline"
                onClick={() => extend.mutate()}
                disabled={extend.isPending || l.plan_type === "unlimited"}
              >
                기간 연장
              </Button>
            </div>
            <Button
              variant="destructive"
              onClick={() => revoke.mutate()}
              disabled={revoke.isPending || l.status === "revoked"}
            >
              라이선스 취소
            </Button>
            <div className="space-y-2 border-t pt-4">
              <Label>메모</Label>
              <Textarea
                value={memoValue}
                onChange={(e) => setMemo(e.target.value)}
              />
              <Button variant="outline" size="sm" onClick={() => saveMemo.mutate()}>
                메모 저장
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>활성화된 기기 (HWID)</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>HWID</TableHead>
                <TableHead>활성화</TableHead>
                <TableHead>최근 접속</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>버전</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {l.activations.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-mono text-xs">{a.hwid}</TableCell>
                  <TableCell>{formatDateTimeKST(a.activated_at)}</TableCell>
                  <TableCell>{formatDateTimeKST(a.last_seen_at)}</TableCell>
                  <TableCell>{a.ip_address ?? "-"}</TableCell>
                  <TableCell>{a.client_version ?? "-"}</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => release.mutate(a.id)}
                    >
                      해제
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {l.activations.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    활성화된 기기가 없습니다.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>감사 로그</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {logs.data?.map((log) => (
              <li key={log.id} className="flex flex-wrap items-center gap-3 text-sm">
                <span className="w-44 shrink-0 text-muted-foreground">
                  {formatDateTimeKST(log.created_at)}
                </span>
                <span className="font-medium">
                  {AUDIT_EVENT_LABELS[log.event_type] ?? log.event_type}
                </span>
                {log.hwid && (
                  <span className="font-mono text-xs text-muted-foreground">
                    {log.hwid.slice(0, 16)}…
                  </span>
                )}
                {log.ip_address && (
                  <span className="text-xs text-muted-foreground">{log.ip_address}</span>
                )}
              </li>
            ))}
            {logs.data?.length === 0 && (
              <li className="text-sm text-muted-foreground">감사 로그가 없습니다.</li>
            )}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
