// app/apply/layout.tsx — 신청 페이지 공통 셸(내비 + 푸터).
import Nav from "@/components/site/Nav";
import Footer from "@/components/site/Footer";

export default function ApplyLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <Nav />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
