// components/StatsReport.tsx  [신규 — 성과 리포트 P1]
// 성과 화면 본문: 숫자 카드(방문·신청·전환율) + 일별 방문 막대(단일 계열, 호버 툴팁, 표 보기) + 유입 경로 표.
// 순수 프레젠테이션(훅 없음). 일별 방문과 신청은 단위가 달라 한 축에 겹치지 않고 툴팁·표로 함께 보여 준다.

import type { Report } from "@/lib/analytics/report";

export default function StatsReport({ report, chartDays }: { report: Report; chartDays: number }) {
  const chart = report.daily.slice(-chartDays);
  const maxViews = Math.max(1, ...chart.map((d) => d.views));
  const maxSourceViews = Math.max(1, ...report.sources.map((s) => s.views));

  return (
    <>
      {/* KPI */}
      <div className="mt-6 grid grid-cols-3 gap-3">
        <Kpi label="방문" value={report.views.toLocaleString("ko-KR")} />
        <Kpi label="신청" value={report.leads.toLocaleString("ko-KR")} />
        <Kpi label="전환율" value={report.conversion === null ? "–" : `${report.conversion}%`} />
      </div>

      {/* 일별 방문 */}
      <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold">일별 방문 (최근 {chartDays}일)</h2>
        {report.views === 0 ? (
          <p className="mt-4 text-sm text-slate-500">아직 방문 기록이 없어요. 아래 채널별 링크로 공유해 보세요.</p>
        ) : (
          <>
            <div className="mt-6 flex h-40 items-end gap-[2px]" role="img" aria-label="일별 방문 막대 차트">
              {chart.map((d) => (
                <div key={d.day} className="group relative flex h-full flex-1 items-end">
                  <div
                    className="w-full rounded-t bg-indigo-500 transition group-hover:bg-indigo-600"
                    style={{ height: d.views ? `${Math.max(2, (d.views / maxViews) * 100)}%` : "0" }}
                  />
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1 text-xs text-white group-hover:block">
                    {shortDay(d.day)} · 방문 {d.views} · 신청 {d.leads}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2 flex justify-between border-t border-slate-200 pt-2 text-xs text-slate-400">
              <span>{shortDay(chart[0].day)}</span>
              <span>{shortDay(chart[chart.length - 1].day)}</span>
            </div>
            <details className="mt-4 text-sm">
              <summary className="cursor-pointer text-slate-500">표로 보기</summary>
              <table className="mt-3 w-full text-left">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1 font-medium">날짜</th>
                    <th className="py-1 text-right font-medium">방문</th>
                    <th className="py-1 text-right font-medium">신청</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {[...chart].reverse().map((d) => (
                    <tr key={d.day}>
                      <td className="py-1">{shortDay(d.day)}</td>
                      <td className="py-1 text-right">{d.views}</td>
                      <td className="py-1 text-right">{d.leads}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        )}
      </section>

      {/* 유입 경로 */}
      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold">유입 경로</h2>
        {report.sources.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">유입 경로 데이터가 아직 없어요.</p>
        ) : (
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="py-2 font-medium">경로</th>
                <th className="py-2 font-medium">방문</th>
                <th className="py-2 text-right font-medium">신청</th>
                <th className="py-2 text-right font-medium">전환율</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {report.sources.map((s) => (
                <tr key={s.source}>
                  <td className="py-2">{s.label}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded bg-slate-100 sm:w-40">
                        <div className="h-full rounded bg-indigo-500" style={{ width: `${(s.views / maxSourceViews) * 100}%` }} />
                      </div>
                      <span>{s.views}</span>
                    </div>
                  </td>
                  <td className="py-2 text-right">{s.leads}</td>
                  <td className="py-2 text-right">{s.conversion === null ? "–" : `${s.conversion}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight">{value}</p>
    </div>
  );
}

/** YYYY-MM-DD → M/D */
function shortDay(day: string): string {
  const [, m, d] = day.split("-");
  return `${Number(m)}/${Number(d)}`;
}
