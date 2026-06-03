"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ProductDistribution } from "@/lib/types";

export function ProductChart({ data }: { data: ProductDistribution[] }) {
  const chartData = data.map((d) => ({ name: d.product_name, 활성: d.active_count }));
  if (chartData.length === 0) {
    return <p className="text-sm text-muted-foreground">활성 키가 없습니다.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData}>
        <XAxis dataKey="name" fontSize={12} tickLine={false} axisLine={false} />
        <YAxis allowDecimals={false} fontSize={12} tickLine={false} axisLine={false} />
        <Tooltip />
        <Bar dataKey="활성" fill="hsl(222.2 47.4% 11.2%)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
