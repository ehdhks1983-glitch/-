// lib/analytics/report.ts  [신규 — 성과 리포트 P1]
// 방문 집계(page_stats)와 신청(leads)을 합쳐 기간 합계·일별·유입 경로별 지표를 만든다.
// 순수 함수(DB 무관) → 대시보드와 검증 스크립트가 같은 로직을 쓴다. 날짜는 한국 시간(KST) 기준.

import { SOURCE_LABELS, TRAFFIC_SOURCES, isTrafficSource, type TrafficSource } from "./source";

export interface StatRow {
  project_id: string;
  day: string; // YYYY-MM-DD (KST)
  source: string;
  views: number;
}

export interface LeadStatRow {
  project_id: string;
  created_at: string;
  meta: { source?: unknown } | null;
}

export interface DailyPoint {
  day: string;
  views: number;
  leads: number;
}

export interface SourcePoint {
  source: TrafficSource;
  label: string;
  views: number;
  leads: number;
  /** 신청/방문(%). 방문이 0이면 null */
  conversion: number | null;
}

export interface Report {
  days: number;
  views: number;
  leads: number;
  conversion: number | null;
  daily: DailyPoint[];
  sources: SourcePoint[];
}

const KST_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" });

/** Date → 한국 시간 기준 YYYY-MM-DD */
export function kstDay(d: Date): string {
  return KST_DAY.format(d);
}

/** today(KST)부터 거꾸로 n일의 날짜 목록(오래된 날 → 오늘). */
export function lastDays(n: number, now = new Date()): string[] {
  const out: string[] = [];
  for (let i = n - 1; i >= 0; i--) out.push(kstDay(new Date(now.getTime() - i * 86_400_000)));
  return out;
}

/** 신청 조회 하한(ISO). KST 날짜 경계를 덮도록 하루 여유를 둔다(범위 밖은 buildReport 가 걸러냄). */
export function leadsSinceIso(days: number, now = new Date()): string {
  return new Date(now.getTime() - (days + 1) * 86_400_000).toISOString();
}

function rate(leads: number, views: number): number | null {
  return views > 0 ? Math.round((leads / views) * 1000) / 10 : null;
}

/** 기간(days) 안의 지표. 범위 밖 행은 무시한다. */
export function buildReport(stats: StatRow[], leads: LeadStatRow[], days: number, now = new Date()): Report {
  const range = lastDays(days, now);
  const inRange = new Set(range);
  const daily = new Map<string, DailyPoint>(range.map((d) => [d, { day: d, views: 0, leads: 0 }]));
  const bySource = new Map<TrafficSource, { views: number; leads: number }>(
    TRAFFIC_SOURCES.map((s) => [s, { views: 0, leads: 0 }]),
  );

  for (const r of stats) {
    if (!inRange.has(r.day)) continue;
    const views = Number(r.views) || 0;
    daily.get(r.day)!.views += views;
    bySource.get(isTrafficSource(r.source) ? r.source : "other")!.views += views;
  }
  for (const l of leads) {
    const day = kstDay(new Date(l.created_at));
    if (!inRange.has(day)) continue;
    daily.get(day)!.leads += 1;
    const src = l.meta?.source;
    bySource.get(isTrafficSource(src) ? src : "other")!.leads += 1;
  }

  const totalViews = [...daily.values()].reduce((a, d) => a + d.views, 0);
  const totalLeads = [...daily.values()].reduce((a, d) => a + d.leads, 0);
  const sources = [...bySource.entries()]
    .filter(([, v]) => v.views > 0 || v.leads > 0)
    .map(([source, v]) => ({ source, label: SOURCE_LABELS[source], ...v, conversion: rate(v.leads, v.views) }))
    .sort((a, b) => b.views - a.views || b.leads - a.leads);

  return {
    days,
    views: totalViews,
    leads: totalLeads,
    conversion: rate(totalLeads, totalViews),
    daily: [...daily.values()],
    sources,
  };
}

/** 프로젝트별 합계(대시보드 목록용). */
export function totalsByProject(stats: StatRow[], leads: LeadStatRow[], days: number, now = new Date()) {
  const inRange = new Set(lastDays(days, now));
  const out = new Map<string, { views: number; leads: number }>();
  const get = (id: string) => out.get(id) ?? out.set(id, { views: 0, leads: 0 }).get(id)!;
  for (const r of stats) if (inRange.has(r.day)) get(r.project_id).views += Number(r.views) || 0;
  for (const l of leads) if (inRange.has(kstDay(new Date(l.created_at)))) get(l.project_id).leads += 1;
  return out;
}
