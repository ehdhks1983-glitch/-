// scripts/test-analytics.ts
// 성과 리포트 검증: 유입 경로 판별 · 기간/일별/경로별 집계를 콘솔에서 확인.
// 실행: npm run test:analytics   (키·DB 불필요)

import assert from "node:assert/strict";
import { detectSource } from "../lib/analytics/source";
import { buildReport, kstDay, lastDays, totalsByProject, type LeadStatRow, type StatRow } from "../lib/analytics/report";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`✅ ${name}`);
}

test("유입 경로: utm > 인앱 > referrer", () => {
  assert.equal(detectSource("https://m.search.naver.com/search", ""), "naver");
  assert.equal(detectSource("https://l.instagram.com/", ""), "instagram");
  assert.equal(detectSource("https://www.threads.net/@shop", ""), "threads");
  assert.equal(detectSource("https://www.google.co.kr/", ""), "google");
  assert.equal(detectSource("", ""), "direct");
  assert.equal(detectSource("https://example.org/post", ""), "other");
  assert.equal(detectSource("https://mysite.com/s/a", "", "", "mysite.com"), "direct");
  assert.equal(detectSource("", "", "Mozilla/5.0 ... KAKAOTALK 10.8.0"), "kakao");
  assert.equal(detectSource("https://m.search.naver.com/", "?utm_source=instagram"), "instagram");
  assert.equal(detectSource("", "?utm_source=flyer"), "other");
});

test("KST 날짜: UTC 15시 이후는 다음 날", () => {
  assert.equal(kstDay(new Date("2026-10-24T14:59:00Z")), "2026-10-24");
  assert.equal(kstDay(new Date("2026-10-24T15:00:00Z")), "2026-10-25");
  const days = lastDays(3, new Date("2026-10-25T03:00:00Z"));
  assert.deepEqual(days, ["2026-10-23", "2026-10-24", "2026-10-25"]);
});

test("집계: 합계·전환율·경로별·범위 밖 제외", () => {
  const now = new Date("2026-10-25T03:00:00Z"); // KST 10/25 12:00
  const stats: StatRow[] = [
    { project_id: "p1", day: "2026-10-25", source: "naver", views: 30 },
    { project_id: "p1", day: "2026-10-24", source: "instagram", views: 10 },
    { project_id: "p1", day: "2026-10-24", source: "bogus", views: 5 }, // 알 수 없는 경로 → 기타
    { project_id: "p1", day: "2026-09-01", source: "naver", views: 999 }, // 범위 밖
  ];
  const leads: LeadStatRow[] = [
    { project_id: "p1", created_at: "2026-10-25T01:00:00Z", meta: { source: "naver" } },
    { project_id: "p1", created_at: "2026-10-24T05:00:00Z", meta: { source: "naver" } },
    { project_id: "p1", created_at: "2026-10-24T06:00:00Z", meta: null }, // 출처 없음 → 기타
  ];
  const r = buildReport(stats, leads, 7, now);
  assert.equal(r.views, 45);
  assert.equal(r.leads, 3);
  assert.equal(r.conversion, 6.7);
  assert.equal(r.daily.length, 7);
  assert.deepEqual(r.daily.at(-1), { day: "2026-10-25", views: 30, leads: 1 });
  assert.deepEqual(
    r.sources.map((s) => [s.source, s.views, s.leads, s.conversion]),
    [
      ["naver", 30, 2, 6.7],
      ["instagram", 10, 0, 0],
      ["other", 5, 1, 20],
    ],
  );
  const t = totalsByProject(stats, leads, 7, now);
  assert.deepEqual(t.get("p1"), { views: 45, leads: 3 });
});

test("방문 0이면 전환율 없음", () => {
  const r = buildReport([], [], 30);
  assert.equal(r.conversion, null);
  assert.equal(r.sources.length, 0);
});

console.log(`\n${passed}개 통과`);
