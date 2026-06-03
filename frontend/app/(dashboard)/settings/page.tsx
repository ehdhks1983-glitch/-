"use client";

import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/store/auth";

export default function SettingsPage() {
  const { user } = useAuth();
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">설정</h1>

      <Card>
        <CardHeader>
          <CardTitle>연결 정보</CardTitle>
          <CardDescription>현재 프론트엔드가 사용하는 API 엔드포인트</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between border-b py-2">
            <span className="text-muted-foreground">API Base URL</span>
            <span className="font-mono">{apiBase}</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-muted-foreground">로그인 계정</span>
            <span className="font-medium">
              {user?.email} ({user?.role === "admin" ? "관리자" : "스탭"})
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>알림 / 만료 정책</CardTitle>
          <CardDescription>
            만료 임박 알림 기준일(기본 3일)과 카톡/이메일 발송은 백엔드 환경변수
            (<span className="font-mono">EXPIRY_NOTIFY_DAYS</span>)와 알림 서비스에서 관리됩니다.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          매일 03:00(UTC) 스케줄러가 만료 키를 정리하고 임박 키 알림을 발송합니다.
          (Phase 3에서 카카오 스킬서버 연동 예정)
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>API 시크릿</CardTitle>
          <CardDescription>제품별 HMAC 시크릿은 제품 관리에서 재발급할 수 있습니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/products" className="text-sm text-primary underline-offset-4 hover:underline">
            제품 관리로 이동 →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
