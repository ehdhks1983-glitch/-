"use client";

// components/workspace/CopyButton.tsx — 클립보드 복사 + 피드백. 비보안 컨텍스트 fallback 포함.

import { useState } from "react";

export default function CopyButton({ text, label = "복사", className = "" }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    const ok = await writeClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }

  return (
    <button
      onClick={copy}
      className={
        className ||
        "rounded-lg border border-stone-200 px-3 py-1.5 text-sm font-medium text-stone-700 transition hover:bg-stone-50"
      }
    >
      {copied ? "복사됨 ✓" : label}
    </button>
  );
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fallthrough to legacy */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
