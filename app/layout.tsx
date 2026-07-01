import type { Metadata } from "next";
import { Noto_Serif_KR, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// 본문(명조) · 캡션(모노). 헤드라인 Pretendard 는 CDN 로드(아래 <link>).
const notoSerif = Noto_Serif_KR({
  variable: "--font-noto-serif",
  weight: ["400", "600", "700"],
  subsets: ["latin"],
  display: "swap",
  preload: false,
});

const jetbrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  display: "swap",
});

const SITE = "https://meomu.kr"; // 운영 도메인 확정 시 교체

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: "머무는순간 — 실제 방문 인증 숏폼 체험단",
  description:
    "가짜 후기 말고, 진짜 하룻밤. 공정위 100% 합법 · 신고 확인된 스테이만 · AI가 아닌 실제 1박 체크인 인증. 감성 독채·풀빌라 전문 숏폼 체험단.",
  keywords: ["숏폼 체험단", "숙박 체험단", "감성 스테이", "독채 펜션", "풀빌라", "공정위 합법", "릴스", "네이버 클립"],
  openGraph: {
    type: "website",
    locale: "ko_KR",
    title: "머무는순간 — 실제 방문 인증 숏폼 체험단",
    description: "가짜 후기 말고, 진짜 하룻밤. 공정위 100% 합법 · 실제 1박 체크인 인증.",
    siteName: "머무는순간",
  },
  twitter: {
    card: "summary_large_image",
    title: "머무는순간 — 실제 방문 인증 숏폼 체험단",
    description: "가짜 후기 말고, 진짜 하룻밤. 공정위 100% 합법 · 실제 1박 체크인 인증.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className={`${notoSerif.variable} ${jetbrains.variable} h-full`}>
      <head>
        {/* Pretendard(헤드라인/UI) — 가변 폰트 CDN */}
        <link
          rel="stylesheet"
          as="style"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"
        />
        {/*
          전환 추적 픽셀 삽입 위치(예: Meta Pixel / GA4 / 네이버 프리미엄로그).
          운영 시 이 위치에 스크립트를 넣으세요.
          <script>...</script>
        */}
      </head>
      <body className="min-h-full flex flex-col bg-ink text-paper antialiased">{children}</body>
    </html>
  );
}
