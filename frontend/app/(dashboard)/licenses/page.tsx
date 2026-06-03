"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { LicenseTable } from "@/components/license-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

export default function LicensesPage() {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [productId, setProductId] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const products = useQuery({ queryKey: ["products"], queryFn: () => api.listProducts() });
  const licenses = useQuery({
    queryKey: ["licenses", { debounced, productId, status, page }],
    queryFn: () =>
      api.listLicenses({
        search: debounced || undefined,
        product_id: productId ? Number(productId) : undefined,
        status: status || undefined,
        page,
        page_size: 20,
      }),
  });

  const data = licenses.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">라이선스 목록</h1>
        <Link href="/licenses/new">
          <Button>키 발급</Button>
        </Link>
      </div>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Input
              placeholder="고객명 / 메모 / 키 prefix 검색"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Select
              value={productId}
              onChange={(e) => {
                setProductId(e.target.value);
                setPage(1);
              }}
            >
              <option value="">전체 제품</option>
              {products.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">전체 상태</option>
              <option value="active">활성</option>
              <option value="revoked">취소됨</option>
              <option value="expired">만료</option>
            </Select>
          </div>

          {licenses.isLoading ? (
            <p className="py-8 text-center text-muted-foreground">로딩 중...</p>
          ) : (
            <LicenseTable data={data?.items ?? []} />
          )}

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">총 {data?.total ?? 0}건</span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                이전
              </Button>
              <span>
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                다음
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
