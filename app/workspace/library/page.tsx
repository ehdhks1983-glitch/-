// app/workspace/library/page.tsx — 내 발행물 목록. §15.10에서 전체 구현.
// 스텝2(셸)에서는 진입점 스캐폴드만.

export default function LibraryPage() {
  return (
    <div>
      <h1 className="text-lg font-bold">내 발행물</h1>
      <p className="mt-1 text-sm text-stone-500">생성한 발행물을 모아보고 다시 열람할 수 있어요.</p>
      <div className="mt-5 rounded-2xl border border-dashed border-stone-300 bg-white p-10 text-center text-sm text-stone-400">
        목록은 다음 단계에서 연결됩니다.
      </div>
    </div>
  );
}
