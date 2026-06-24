// app/workspace/library/[id]/page.tsx — 발행물 재열람 (스펙 §10/§15.10).

import GenerationDetail from "@/components/workspace/GenerationDetail";

export default async function LibraryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GenerationDetail id={id} />;
}
