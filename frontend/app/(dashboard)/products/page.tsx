"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogDescription, DialogTitle } from "@/components/ui/dialog";
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
import type { ProductWithSecret } from "@/lib/types";

const EMPTY = { code: "", name: "", prefix: "", max_hwid_count: "1", description: "" };

export default function ProductsPage() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [secretProduct, setSecretProduct] = useState<ProductWithSecret | null>(null);
  const [error, setError] = useState<string | null>(null);

  const products = useQuery({ queryKey: ["products"], queryFn: () => api.listProducts() });

  const create = useMutation({
    mutationFn: () =>
      api.createProduct({
        code: form.code,
        name: form.name,
        prefix: form.prefix,
        description: form.description || null,
        max_hwid_count: Number(form.max_hwid_count) || 1,
      }),
    onSuccess: (p) => {
      setCreateOpen(false);
      setForm({ ...EMPTY });
      setSecretProduct(p);
      qc.invalidateQueries({ queryKey: ["products"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "생성 실패"),
  });

  const rotate = useMutation({
    mutationFn: (id: number) => api.rotateSecret(id),
    onSuccess: (p) => setSecretProduct(p),
  });

  async function showSecret(id: number) {
    setSecretProduct(await api.getProduct(id));
  }

  function copy(text: string) {
    navigator.clipboard.writeText(text).catch((e) => console.error(e));
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">제품 관리</h1>
        <Button
          onClick={() => {
            setError(null);
            setCreateOpen(true);
          }}
        >
          제품 추가
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>코드</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>기본 HWID 수</TableHead>
                <TableHead>상태</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.data?.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell className="font-mono">{p.code}</TableCell>
                  <TableCell className="font-mono">{p.prefix}</TableCell>
                  <TableCell>{p.max_hwid_count}</TableCell>
                  <TableCell>
                    {p.is_active ? (
                      <Badge variant="success">활성</Badge>
                    ) : (
                      <Badge variant="secondary">비활성</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button variant="outline" size="sm" onClick={() => showSecret(p.id)}>
                      시크릿 / 재발급
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {products.data?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    등록된 제품이 없습니다.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)}>
        <DialogTitle>제품 추가</DialogTitle>
        <div className="mt-4 space-y-3">
          <div className="space-y-1">
            <Label>이름</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="센텀라이터"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>코드</Label>
              <Input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                placeholder="centum-writer"
              />
            </div>
            <div className="space-y-1">
              <Label>Prefix (2자)</Label>
              <Input
                value={form.prefix}
                onChange={(e) => setForm({ ...form, prefix: e.target.value })}
                placeholder="CW"
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label>기본 HWID 등록 수</Label>
            <Input
              type="number"
              min={1}
              value={form.max_hwid_count}
              onChange={(e) => setForm({ ...form, max_hwid_count: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label>설명</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setCreateOpen(false)}>
            취소
          </Button>
          <Button onClick={() => create.mutate()} disabled={create.isPending}>
            생성
          </Button>
        </div>
      </Dialog>

      {/* Secret dialog */}
      <Dialog open={secretProduct !== null} onClose={() => setSecretProduct(null)}>
        <DialogTitle>{secretProduct?.name} — HMAC 시크릿</DialogTitle>
        <DialogDescription>
          봇 클라이언트의 환경변수로만 보관하세요. 재발급 시 기존 봇은 갱신이 필요합니다.
        </DialogDescription>
        <div className="mt-4 space-y-3">
          <div className="break-all rounded-md border bg-secondary/40 p-3 font-mono text-sm">
            {secretProduct?.secret_key}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => secretProduct && copy(secretProduct.secret_key)}
            >
              복사
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => secretProduct && rotate.mutate(secretProduct.id)}
              disabled={rotate.isPending}
            >
              시크릿 재발급
            </Button>
          </div>
        </div>
        <div className="mt-6 flex justify-end">
          <Button onClick={() => setSecretProduct(null)}>닫기</Button>
        </div>
      </Dialog>
    </div>
  );
}
