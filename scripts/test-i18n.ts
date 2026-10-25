// scripts/test-i18n.ts
// 외국인 손님 패키지 검증: 매장 정보·지도 링크·JSON-LD 이스케이프·번역본 정리·5개 언어 문구 완비·(목) 번역.
// 실행: npm run test:i18n   (키·DB 불필요 — 번역은 목 모드)

process.env.PROMPTSITE_MOCK = "1";

import assert from "node:assert/strict";
import { FOREIGN_LANGS, type PageLang } from "../lib/i18n/langs";
import { uiText } from "../lib/i18n/ui";
import { hasPlace, jsonLdString, localBusinessJsonLd, mapLinks, parsePlace } from "../lib/i18n/place";
import { parseTranslations } from "../lib/i18n/translations";
import { aiOutputLabel } from "../lib/compliance/notice";
import { consentText, leadConsentItems } from "../lib/compliance/privacy";
import { translateCopy } from "../lib/ai/translateCopy";

const ALL: PageLang[] = ["ko", ...FOREIGN_LANGS];

let passed = 0;
async function test(name: string, fn: () => void | Promise<void>) {
  await fn();
  passed++;
  console.log(`✅ ${name}`);
}

function nonEmptyStrings(obj: unknown, path = ""): string[] {
  if (typeof obj === "string") return obj.trim() ? [] : [path];
  if (obj && typeof obj === "object") return Object.entries(obj).flatMap(([k, v]) => nonEmptyStrings(v, `${path}.${k}`));
  return [];
}

async function main() {
  await test("매장 정보 정리·지도 링크", () => {
    const p = parsePlace({ name: " 서면 수제청 ", address: "부산 부산진구 서면로 1", phone: "051-000-0000", hours: "", junk: "x" });
    assert.deepEqual(p, { name: "서면 수제청", address: "부산 부산진구 서면로 1", phone: "051-000-0000" });
    assert.ok(hasPlace(p));
    assert.ok(!hasPlace({ name: "이름만" }));
    const links = mapLinks(p)!;
    assert.ok(links.naver.startsWith("https://map.naver.com/p/search/"));
    assert.ok(links.google.includes(encodeURIComponent("서면 수제청 부산 부산진구 서면로 1")));
    assert.equal(mapLinks({ name: "주소 없음" }), null);
  });

  await test("JSON-LD: LocalBusiness + </script> 탈출 방지", () => {
    const ld = localBusinessJsonLd({ name: "가게</script><script>alert(1)</script>", address: "서울" }, { url: "https://x.kr/s/a", lang: "ko", description: "" });
    const s = jsonLdString(ld);
    assert.ok(!s.includes("</script>"));
    assert.ok(s.includes('"@type":"LocalBusiness"'));
  });

  await test("번역본 정리: 모르는 언어·빈 문구 제거, 해시태그 정리", () => {
    const copy = { hero: { headline: "Hello", subheadline: "", cta: "Go" }, problem: {}, solution: {}, features: { items: [] }, faq: [], cta: {} };
    const t = parseTranslations({
      en: { copy, summary: "A cafe.", hashtags: ["cafe", "#busan trip", ""], hours: "Daily" },
      ja: { copy: { hero: { headline: "" } } },
      fr: { copy },
    });
    assert.deepEqual(Object.keys(t), ["en"]);
    assert.deepEqual(t.en!.hashtags, ["#cafe", "#busantrip"]);
    assert.equal(t.en!.copy.hero.headline, "Hello");
  });

  await test("5개 언어 화면 문구·AI 표시·동의 고지 완비", () => {
    for (const l of ALL) {
      assert.deepEqual(nonEmptyStrings(uiText(l)), [], `uiText ${l}`);
      assert.ok(aiOutputLabel(l).length > 10, `ai label ${l}`);
      assert.ok(consentText(l).label && consentText(l).required);
      assert.equal(leadConsentItems("가게", l).length, 5);
      assert.equal(leadConsentItems("", l)[0].value.length > 0, true);
    }
    assert.notEqual(uiText("ja").signup.submit, uiText("ko").signup.submit);
  });

  await test("(목) 번역 결과 구조", async () => {
    const copy = { hero: { headline: "퇴근 후 30분", subheadline: "", cta: "신청" }, problem: { title: "", body: "" }, solution: { title: "", body: "" }, features: { title: "", items: [] }, faq: [], cta: { headline: "", button: "신청" } };
    const t = await translateCopy(copy, "en", { serviceName: "핏코치" });
    assert.ok(t.copy.hero.headline);
    assert.ok(t.hashtags.every((h) => h.startsWith("#")));
  });

  console.log(`\n${passed}개 통과`);
}

main().catch((err) => {
  console.error("❌", err);
  process.exit(1);
});
