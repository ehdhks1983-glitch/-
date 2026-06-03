"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { IssuedKeyModal } from "@/components/issued-key-modal";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, type IssuePayload, api, issueBulkCsv } from "@/lib/api";
import type { BulkIssueResponse, LicenseIssueResponse, PlanType } from "@/lib/types";

const schema = z
  .object({
    product_id: z.string().min(1, "제품을 선택하세요."),
    plan_type: z.enum(["trial_7", "monthly_30", "unlimited", "custom"]),
    duration_days: z.string().optional(),
    customer_name: z.string().optional(),
    customer_contact: z.string().optional(),
    memo: z.string().optional(),
    count: z.string().optional(),
  })
  .superRefine((val, ctx) => {
    if (val.plan_type === "custom" && (!val.duration_days || Number(val.duration_days) < 1)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["duration_days"],
        message: "커스텀 플랜은 일수를 입력하세요.",
      });
    }
  });
type FormValues = z.infer<typeof schema>;

export default function NewLicensePage() {
  const [mode, setMode] = useState<"single" | "bulk">("single");
  const [error, setError] = useState<string | null>(null);
  const [single, setSingle] = useState<LicenseIssueResponse | null>(null);
  const [bulk, setBulk] = useState<BulkIssueResponse | null>(null);

  const products = useQuery({ queryKey: ["products"], queryFn: () => api.listProducts() });

  const {
    register,
    handleSubmit,
    watch,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { plan_type: "monthly_30", count: "10" },
  });

  const planType = watch("plan_type");

  function buildPayload(v: FormValues): IssuePayload {
    return {
      product_id: Number(v.product_id),
      plan_type: v.plan_type as PlanType,
      duration_days: v.plan_type === "custom" ? Number(v.duration_days) : null,
      customer_name: v.customer_name || null,
      customer_contact: v.customer_contact || null,
      memo: v.memo || null,
    };
  }

  const issueSingle = useMutation({
    mutationFn: (v: FormValues) => api.issueLicense(buildPayload(v)),
    onSuccess: (res) => setSingle(res),
    onError: (e) => setError(e instanceof ApiError ? e.message : "발급 실패"),
  });

  const issueBulk = useMutation({
    mutationFn: (v: FormValues) =>
      api.issueBulk({ ...buildPayload(v), count: Number(v.count || 1) }),
    onSuccess: (res) => setBulk(res),
    onError: (e) => setError(e instanceof ApiError ? e.message : "일괄 발급 실패"),
  });

  function onSubmit(v: FormValues) {
    setError(null);
    setBulk(null);
    if (mode === "single") issueSingle.mutate(v);
    else issueBulk.mutate(v);
  }

  async function downloadCsv() {
    const v = getValues();
    const blob = await issueBulkCsv({ ...buildPayload(v), count: Number(v.count || 1) });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "licenses.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const selectedProduct = products.data?.find(
    (p) => String(p.id) === watch("product_id")
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">키 발급</h1>

      <Tabs
        value={mode}
        onValueChange={(v) => setMode(v as "single" | "bulk")}
        options={[
          { value: "single", label: "단건 발급" },
          { value: "bulk", label: "일괄 발급" },
        ]}
      />

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>{mode === "single" ? "단건 발급" : "일괄 발급"}</CardTitle>
          <CardDescription>
            {mode === "single"
              ? "고객 1명에게 발급할 키를 생성합니다."
              : "여러 개의 키를 한 번에 생성하고 CSV로 받을 수 있습니다."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label>제품</Label>
              <Select {...register("product_id")}>
                <option value="">제품 선택</option>
                {products.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.prefix})
                  </option>
                ))}
              </Select>
              {errors.product_id && (
                <p className="text-sm text-destructive">{errors.product_id.message}</p>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>플랜</Label>
                <Select {...register("plan_type")}>
                  <option value="trial_7">7일 체험</option>
                  <option value="monthly_30">30일</option>
                  <option value="unlimited">무제한</option>
                  <option value="custom">커스텀</option>
                </Select>
              </div>
              {planType === "custom" && (
                <div className="space-y-2">
                  <Label>일수</Label>
                  <Input type="number" min={1} {...register("duration_days")} />
                  {errors.duration_days && (
                    <p className="text-sm text-destructive">
                      {errors.duration_days.message}
                    </p>
                  )}
                </div>
              )}
              {mode === "bulk" && (
                <div className="space-y-2">
                  <Label>발급 수량</Label>
                  <Input type="number" min={1} max={1000} {...register("count")} />
                </div>
              )}
            </div>

            {mode === "single" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>고객명</Label>
                  <Input {...register("customer_name")} />
                </div>
                <div className="space-y-2">
                  <Label>고객 연락처 (카톡 ID / 이메일)</Label>
                  <Input {...register("customer_contact")} />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>메모</Label>
              <Textarea {...register("memo")} />
            </div>

            {error && (
              <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <div className="flex gap-2">
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "발급 중..." : "발급"}
              </Button>
              {mode === "bulk" && (
                <Button type="button" variant="outline" onClick={downloadCsv}>
                  CSV로 발급·다운로드
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {mode === "bulk" && bulk && (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>발급 완료 — {bulk.count}건</CardTitle>
            <CardDescription>아래 키들은 지금만 확인할 수 있습니다.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="max-h-72 space-y-1 overflow-auto font-mono text-sm">
              {bulk.keys.map((k) => (
                <div key={k.license_id} className="rounded bg-secondary/40 px-2 py-1">
                  {k.raw_key}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <IssuedKeyModal
        open={single !== null}
        onClose={() => setSingle(null)}
        result={single}
        productName={selectedProduct?.name}
        customerName={getValues("customer_name")}
      />
    </div>
  );
}
