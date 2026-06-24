// app/workspace/page.tsx — 새 발행 (컨피규레이터 + 결과). §15.8에서 전체 구현.
// 스텝2(셸)에서는 진입점 스캐폴드만. 실제 폼/생성/결과 탭은 이후 단계에서 채운다.

export default function NewPublishPage() {
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      {/* 컨피규레이터(좌) — §15.8에서 폼 구현 */}
      <section className="rounded-2xl border border-stone-200 bg-white p-5">
        <h1 className="text-lg font-bold">새 발행</h1>
        <p className="mt-1 text-sm text-stone-500">
          키워드와 참고자료를 넣으면 코어를 뽑아 블로그 + 4채널을 만들어요.
        </p>
        <div className="mt-4 rounded-xl border border-dashed border-stone-300 p-4 text-sm text-stone-400">
          컨피규레이터(키워드·참고 URL·톤·채널 선택)는 다음 단계에서 연결됩니다.
        </div>
      </section>

      {/* 메인(우) — 빈 상태 안내 (스펙 §10) */}
      <section className="flex min-h-[320px] items-center justify-center rounded-2xl border border-stone-200 bg-white p-8 text-center">
        <div>
          <div className="text-4xl">🐻</div>
          <p className="mt-3 font-semibold">아직 만든 글이 없어요</p>
          <p className="mt-1 text-sm text-stone-500">
            왼쪽에서 키워드를 넣고 <b>생성</b>을 누르면 여기에 결과가 나타납니다.
          </p>
        </div>
      </section>
    </div>
  );
}
