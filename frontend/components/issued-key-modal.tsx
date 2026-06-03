"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { LicenseIssueResponse } from "@/lib/types";
import { PLAN_LABELS, formatDateKST } from "@/lib/utils";

export function IssuedKeyModal({
  open,
  onClose,
  result,
  productName,
  customerName,
}: {
  open: boolean;
  onClose: () => void;
  result: LicenseIssueResponse | null;
  productName?: string;
  customerName?: string;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  if (!result) return null;

  const expires = formatDateKST(result.expires_at);
  const template = `안녕하세요 ${customerName || "고객"}님, ${productName ?? ""} ${
    PLAN_LABELS[result.plan_type]
  } 라이선스입니다.\n키: ${result.raw_key}\n만료: ${expires}`;

  async function copy(text: string, tag: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(tag);
      setTimeout(() => setCopied(null), 1500);
    } catch (e) {
      console.error("클립보드 복사 실패", e);
    }
  }

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>발급 완료</DialogTitle>
      <DialogDescription>
        키 원본은 지금만 확인할 수 있습니다. 복사해서 안전하게 전달하세요.
      </DialogDescription>
      <div className="mt-4 space-y-3">
        <div className="break-all rounded-md border bg-secondary/40 p-3 font-mono text-sm">
          {result.raw_key}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => copy(result.raw_key, "key")}>
            {copied === "key" ? (
              <Check className="h-4 w-4" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            키 복사
          </Button>
          <Button variant="outline" size="sm" onClick={() => copy(template, "tpl")}>
            {copied === "tpl" ? (
              <Check className="h-4 w-4" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            카톡 메시지 템플릿 복사
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">만료: {expires}</p>
      </div>
      <div className="mt-6 flex justify-end">
        <Button onClick={onClose}>닫기</Button>
      </div>
    </Dialog>
  );
}
