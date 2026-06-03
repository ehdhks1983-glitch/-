"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useRouter } from "next/navigation";

import { StatusBadge } from "@/components/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { License } from "@/lib/types";
import { PLAN_LABELS, formatDateKST } from "@/lib/utils";

const columns: ColumnDef<License>[] = [
  {
    id: "key",
    header: "키 prefix",
    cell: ({ row }) => <span className="font-mono">{row.original.key_prefix}…</span>,
  },
  { id: "product", header: "제품", cell: ({ row }) => row.original.product_code ?? "-" },
  { id: "plan", header: "플랜", cell: ({ row }) => PLAN_LABELS[row.original.plan_type] },
  { id: "customer", header: "고객", cell: ({ row }) => row.original.customer_name ?? "-" },
  {
    id: "hwid",
    header: "HWID",
    cell: ({ row }) => `${row.original.hwid_used}/${row.original.hwid_max}`,
  },
  { id: "issued", header: "발급일", cell: ({ row }) => formatDateKST(row.original.issued_at) },
  { id: "expires", header: "만료", cell: ({ row }) => formatDateKST(row.original.expires_at) },
  {
    id: "status",
    header: "상태",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
];

export function LicenseTable({ data }: { data: License[] }) {
  const router = useRouter();
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((hg) => (
          <TableRow key={hg.id}>
            {hg.headers.map((h) => (
              <TableHead key={h.id}>
                {flexRender(h.column.columnDef.header, h.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow
            key={row.id}
            className="cursor-pointer"
            onClick={() => router.push(`/licenses/${row.original.id}`)}
          >
            {row.getVisibleCells().map((cell) => (
              <TableCell key={cell.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
        {data.length === 0 && (
          <TableRow>
            <TableCell colSpan={columns.length} className="text-center text-muted-foreground">
              결과가 없습니다.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
