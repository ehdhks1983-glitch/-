// scripts/threads-test/02-validate.ts
// 가상 테스트 2 — 입력 검증(lib/threads/validate). 순수 함수라 네트워크/DB 불필요.
// 실행: npx tsx scripts/threads-test/02-validate.ts

import { ok, eq, summary } from "./_assert";
import {
  cleanText,
  isValidText,
  parseMediaType,
  parseImageUrl,
  parseFutureISO,
} from "../../lib/threads/validate";
import { THREADS_MAX_TEXT } from "../../lib/threads/config";

console.log("STEP 2 — lib/threads/validate.ts (가상 테스트)\n");

// cleanText
eq("cleanText trims", cleanText("  hi  "), "hi");
eq("cleanText non-string → ''", cleanText(123), "");
eq("cleanText null → ''", cleanText(null), "");

// isValidText (기본 한도 500)
ok("빈 글 무효", isValidText("") === false);
ok("공백만은 cleanText 후 무효", isValidText(cleanText("   ")) === false);
ok("정상 글 유효", isValidText("안녕하세요") === true);
ok(`정확히 ${THREADS_MAX_TEXT}자 유효`, isValidText("a".repeat(THREADS_MAX_TEXT)) === true);
ok(`${THREADS_MAX_TEXT + 1}자 무효`, isValidText("a".repeat(THREADS_MAX_TEXT + 1)) === false);

// parseMediaType
eq("IMAGE → IMAGE", parseMediaType("IMAGE"), "IMAGE");
eq("TEXT → TEXT", parseMediaType("TEXT"), "TEXT");
eq("알 수 없음 → TEXT", parseMediaType("VIDEO"), "TEXT");
eq("undefined → TEXT", parseMediaType(undefined), "TEXT");

// parseImageUrl
eq("https 허용", parseImageUrl("https://img.example/a.jpg"), "https://img.example/a.jpg");
ok("http 허용", parseImageUrl("http://img.example/a.jpg") !== null);
eq("javascript: 차단", parseImageUrl("javascript:alert(1)"), null);
eq("상대경로 차단", parseImageUrl("/local/a.jpg"), null);
eq("빈 값 → null", parseImageUrl(""), null);
eq("비문자열 → null", parseImageUrl(42), null);

// parseFutureISO
const future = new Date(Date.now() + 3600_000).toISOString();
ok("미래 시각 통과", parseFutureISO(future) !== null);
eq("미래 시각 ISO 정규화", parseFutureISO(future), new Date(future).toISOString());
eq("과거 시각 → null", parseFutureISO("2020-01-01T00:00:00.000Z"), null);
eq("잘못된 값 → null", parseFutureISO("내일쯤"), null);
eq("비문자열 → null", parseFutureISO(123), null);

summary("STEP 2 — validate.ts");
