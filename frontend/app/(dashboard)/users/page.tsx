"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { formatDateTimeKST } from "@/lib/utils";

const EMPTY = { email: "", password: "", name: "", role: "staff" };

export default function UsersPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);

  const users = useQuery({ queryKey: ["users"], queryFn: () => api.listUsers() });
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });

  const create = useMutation({
    mutationFn: () =>
      api.createUser({
        email: form.email,
        password: form.password,
        name: form.name || null,
        role: form.role,
      }),
    onSuccess: () => {
      setForm({ ...EMPTY });
      setError(null);
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "생성 실패"),
  });

  const toggleActive = useMutation({
    mutationFn: (u: { id: number; is_active: boolean }) =>
      api.updateUser(u.id, { is_active: !u.is_active }),
    onSuccess: refresh,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">계정 관리</h1>

      <Card>
        <CardHeader>
          <CardTitle>스탭 추가</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid items-end gap-3 sm:grid-cols-5">
            <div className="space-y-1">
              <Label>이메일</Label>
              <Input
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label>비밀번호</Label>
              <Input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label>이름</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label>권한</Label>
              <Select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                <option value="staff">스탭</option>
                <option value="admin">관리자</option>
              </Select>
            </div>
            <Button onClick={() => create.mutate()} disabled={create.isPending}>
              추가
            </Button>
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이메일</TableHead>
                <TableHead>이름</TableHead>
                <TableHead>권한</TableHead>
                <TableHead>최근 로그인</TableHead>
                <TableHead>상태</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data?.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>{u.name ?? "-"}</TableCell>
                  <TableCell>
                    <Badge variant={u.role === "admin" ? "default" : "secondary"}>
                      {u.role === "admin" ? "관리자" : "스탭"}
                    </Badge>
                  </TableCell>
                  <TableCell>{formatDateTimeKST(u.last_login_at)}</TableCell>
                  <TableCell>
                    {u.is_active ? (
                      <Badge variant="success">활성</Badge>
                    ) : (
                      <Badge variant="secondary">비활성</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        toggleActive.mutate({ id: u.id, is_active: u.is_active })
                      }
                    >
                      {u.is_active ? "비활성화" : "활성화"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
