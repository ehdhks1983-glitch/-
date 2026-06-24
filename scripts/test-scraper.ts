// scripts/test-scraper.ts — §16 검증: 스크래퍼 본문 추출(네이버 모바일 경로) + URL 정규화 + 실패 처리.
// 결정적 픽스처(네트워크 무관)로 파싱을 검증. 라이브 검증은 SCRAPER_LIVE_URL 환경변수로 선택.
// 실행: npm run test:scraper  [URL]

import { config as loadEnv } from "dotenv";
loadEnv({ path: ".env.local" });

import { extractText, extractTitle } from "@/lib/scraper/extract";
import { GENERIC_SELECTORS, SITE_RULES } from "@/lib/scraper/config";
import { scrapeUrl } from "@/lib/scraper";
import { assertPublicUrl } from "@/lib/scraper/ssrf";

const BODY =
  "곰탕은 사골과 양지를 오래 끓여 만든 한국의 대표 보양식입니다. " +
  "핵심은 불 조절과 시간인데, 센 불로 끓인 뒤 약불에서 최소 여섯 시간을 우려야 깊은 맛이 납니다. " +
  "중간중간 떠오르는 기름과 거품을 걷어내면 국물이 한층 맑고 깔끔해집니다. " +
  "처음 끓일 때 한 번 데쳐 핏물을 빼는 과정이 누린내를 잡는 가장 중요한 단계입니다.";

// 네이버 모바일 블로그 모사: 잡음(script/nav/댓글) + 본문 div.se-main-container
const NAVER_MOBILE_FIXTURE = `<!doctype html><html><head><title>곰탕 끓이는 법 — 블로그</title>
<meta property="og:title" content="실패 없는 곰탕 끓이는 법"></head>
<body>
<script>var x=1;</script>
<nav>네이버 블로그 메뉴 홈 이웃</nav>
<div id="mainFrame"></div>
<div class="se-main-container">
  <p class="se-text"><span>${BODY}</span></p>
  <p class="se-text"><span>마지막으로 소금과 후추는 먹기 직전에 각자 입맛에 맞게 더하는 것이 좋습니다.</span></p>
</div>
<div class="u_cbox">댓글 234개 좋아요</div>
<footer>Copyright Naver</footer>
</body></html>`;

const GENERIC_FIXTURE = `<!doctype html><html><head><title>기사 제목</title></head><body>
<header>사이트 헤더 광고</header>
<article>
  <h1>기사 본문 제목</h1>
  <p>${BODY}</p>
</article>
<aside>관련기사 추천</aside></body></html>`;

let fail = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "✅" : "❌"} ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fail++;
}

async function main() {
  const naverRule = SITE_RULES.find((r) => r.id === "naver-blog")!;
  const selectors = [...naverRule.selectors, ...GENERIC_SELECTORS];

  // 1) 네이버 모바일 본문 추출
  const n = extractText(NAVER_MOBILE_FIXTURE, selectors);
  check("네이버 본문 추출(se-main-container)", n.selector === "div.se-main-container", `selector=${n.selector}`);
  check("본문 길이 충분", n.text.length >= 200, `${n.text.length}자`);
  check("본문 내용 포함", n.text.includes("사골과 양지"));
  check("잡음 제거(댓글/메뉴 미포함)", !n.text.includes("댓글 234개") && !n.text.includes("이웃"));

  // 2) 제목 추출(og:title 우선)
  check("제목 추출(og:title)", extractTitle(NAVER_MOBILE_FIXTURE) === "실패 없는 곰탕 끓이는 법");

  // 3) 일반 기사 추출
  const g = extractText(GENERIC_FIXTURE, GENERIC_SELECTORS);
  check("일반 기사 추출(article)", g.selector === "article" && g.text.includes("사골과 양지"));

  // 4) URL 정규화: blog.naver.com → m.blog.naver.com
  const u = new URL("https://blog.naver.com/foodlover/223123456789");
  const rule = SITE_RULES.find((r) => r.test.test(u.hostname));
  rule?.toMobile?.(u);
  check("네이버 URL 모바일 정규화", u.hostname === "m.blog.naver.com" && rule?.iframe === "#mainFrame");

  // 5) 잘못된 URL → ok:false (throw 안 함)
  const bad = await scrapeUrl("그냥-텍스트");
  check("잘못된 URL 안전 처리", bad.ok === false && bad.via === "none");

  // 5b) SSRF 방어: 내부/사설/메타데이터 차단, 공개 IP 허용 (네트워크 불필요 — IP 리터럴)
  const blocked = ["http://localhost/", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://10.1.2.3/", "http://192.168.0.1/", "http://[::1]/", "ftp://example.com/"];
  let allBlocked = true;
  for (const u of blocked) {
    let threw = false;
    try { await assertPublicUrl(u); } catch { threw = true; }
    if (!threw) { allBlocked = false; console.log("   미차단:", u); }
  }
  check("SSRF: 내부/사설/메타데이터/비http 차단", allBlocked);
  let publicOk = true;
  try { await assertPublicUrl("http://8.8.8.8/"); } catch { publicOk = false; }
  check("SSRF: 공개 IP 허용", publicOk);

  // 6) (선택) 라이브 스크랩
  const live = process.argv[2] || process.env.SCRAPER_LIVE_URL;
  if (live) {
    console.log(`\n── 라이브 스크랩: ${live} ──`);
    const r = await scrapeUrl(live);
    console.log(`ok=${r.ok} via=${r.via} chars=${r.chars} note=${r.note ?? ""}`);
    console.log((r.text || "").slice(0, 300));
  }

  console.log(fail === 0 ? "\n✅ 스크래퍼 검증 통과" : `\n❌ ${fail}건 실패`);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("❌ 스크래퍼 검증 오류:", e);
  process.exit(1);
});
