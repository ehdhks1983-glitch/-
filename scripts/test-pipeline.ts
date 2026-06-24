// scripts/test-pipeline.ts — §16 검증: 파이프라인(키워드+참고 → core → 블로그) + 코어룰.
//   · core 생성: facts에 출처 없는 항목 없음 / 참고자료 없으면 facts=[]
//   · 블로그: 핵심태그 정확히 10개
//   · 워커 E2E: queued → done, core+블로그 산출물 저장
// 키리스 목 모드로 동작(네트워크 불필요: sourceUrls=[]).
// 실행: npm run test:pipeline

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });
process.env.GOMDAERI_MOCK = "1"; // 결정적 검증

import { extractCore } from "@/lib/pipeline/core";
import { generateBlog, BLOG_TAG_COUNT } from "@/lib/pipeline/channels/blog";
import { memoryStore, __resetMemoryStore } from "@/lib/store/memory";
import { drainOnce } from "@/lib/worker/loop";
import { latestOutputs } from "@/lib/store/types";
import { ALL_CHANNELS, type CafeContent, type GenOptions, type InstagramContent, type ShortsContent, type ThreadsContent } from "@/lib/multipublish/types";

const OPTS: GenOptions = { tone: 60, monetize: true, channels: ["blog"] };
let fail = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "✅" : "❌"} ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fail++;
}

async function main() {
  // ── 코어: 참고자료 있을 때 facts에 출처 ──
  const withSrc = await extractCore({
    keyword: "곰탕",
    options: OPTS,
    sources: [{ url: "https://m.blog.naver.com/foodie/123", text: "곰탕은 사골을 오래 끓인다." }],
  });
  check("core_message 존재", withSrc.core.core_message.length > 0);
  check("angles 3개 이상", withSrc.core.angles.length >= 3, `${withSrc.core.angles.length}개`);
  check("facts 모두 출처 있음", withSrc.core.facts.every((f) => f.claim && f.source), `${withSrc.core.facts.length}건`);
  check("costUsd 계산됨", withSrc.costUsd >= 0);

  // ── 코어: 참고자료 없으면 facts=[] (근거 없음) ──
  const noSrc = await extractCore({ keyword: "삼계탕", options: OPTS, sources: [] });
  check("참고자료 없으면 facts 빈 배열", noSrc.core.facts.length === 0);

  // ── 블로그: 핵심태그 정확히 10개 ──
  const blog = await generateBlog(withSrc.core, { keyword: "곰탕", options: OPTS });
  check(`블로그 태그 정확히 ${BLOG_TAG_COUNT}개`, blog.content.tags.length === BLOG_TAG_COUNT, `${blog.content.tags.length}개`);
  check("태그 모두 비어있지 않음/중복없음", new Set(blog.content.tags).size === BLOG_TAG_COUNT && blog.content.tags.every(Boolean));
  check("제목/본문/메타 존재", !!blog.content.title && blog.content.body_markdown.length > 50 && !!blog.content.meta_description);
  check("썸네일 1:1 가이드", /1:1|정사각/.test(blog.content.thumbnail_guide));

  // ── 워커 E2E: 전 채널(블로그+4채널) queued → done ──
  __resetMemoryStore();
  const rec = await memoryStore.create({
    owner: "u1",
    keyword: "곰탕 끓이는 법",
    sourceUrls: [],
    options: { tone: 60, monetize: true, channels: ALL_CHANNELS },
  });
  await drainOnce();
  const done = await memoryStore.getById(rec.id);
  check("워커 처리 done", done?.status === "done", `status=${done?.status}`);
  check("core 저장됨", !!done?.core?.core_message);
  check("제목 자동 설정", !!done?.title && done.title.length > 0, done?.title);

  const outs = latestOutputs(done?.outputs ?? []);
  check("5개 채널 산출물", outs.length === 5 && outs.every((o) => o.status === "done"), `${outs.length}개`);

  const blogOut = outs.find((o) => o.channel === "blog");
  check("블로그: 태그 10개", !!blogOut && (blogOut.content as { tags: string[] }).tags.length === BLOG_TAG_COUNT);

  const th = outs.find((o) => o.channel === "threads")?.content as ThreadsContent | undefined;
  check("스레드: posts 1~6 / 해시태그 ≤2", !!th && th.posts.length >= 1 && th.posts.length <= 6 && th.hashtags.length <= 2);

  const ig = outs.find((o) => o.channel === "instagram")?.content as InstagramContent | undefined;
  check("인스타: 해시태그 10~20 / 캐러셀 ≥1", !!ig && ig.hashtags.length >= 10 && ig.hashtags.length <= 20 && ig.carousel.length >= 1, `해시태그 ${ig?.hashtags.length}`);

  const cafe = outs.find((o) => o.channel === "cafe")?.content as CafeContent | undefined;
  check("카페: 제목/본문/댓글유도", !!cafe && !!cafe.title && !!cafe.body && !!cafe.comment_bait);

  const sh = outs.find((o) => o.channel === "shorts")?.content as ShortsContent | undefined;
  check("쇼츠: 장면 ≥1 / 길이 30~60초", !!sh && sh.scenes.length >= 1 && sh.duration_sec >= 30 && sh.duration_sec <= 60, `${sh?.duration_sec}초`);

  console.log(fail === 0 ? "\n✅ 파이프라인(코어→블로그+4채널) 검증 통과" : `\n❌ ${fail}건 실패`);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("❌ 파이프라인 검증 오류:", e);
  process.exit(1);
});
