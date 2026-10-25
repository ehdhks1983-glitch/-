// scripts/test-compliance.ts
// 컴플라이언스 P0 검증: 업종 감지 · 금칙어 검사 · 게시 전 승인 검증을 콘솔에서 확인.
// 실행: npm run test:compliance   (키·DB 불필요)

import assert from "node:assert/strict";
import type { BizInfo, SectionCopy } from "../lib/ai/types";
import { detectIndustry, type IndustryId } from "../lib/compliance/industries";
import { checkCopy, hasBlocking } from "../lib/compliance/check";
import { parseApproval, validateApproval } from "../lib/compliance/approval";
import { buildRulesFeed } from "../lib/compliance/feed";
import { RULES } from "../lib/compliance/rules";

function copyWith(headline: string, body = ""): SectionCopy {
  return {
    hero: { headline, subheadline: "", cta: "신청하기" },
    problem: { title: "", body },
    solution: { title: "", body: "" },
    features: { title: "", items: [] },
    faq: [],
    cta: { headline: "", button: "신청하기" },
  };
}

function biz(service_name: string): BizInfo {
  return {
    service_name,
    target_customer: "",
    main_problem: "",
    solution: "",
    cta: "",
    tone: "",
    language: "ko",
    missing: [],
  };
}

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`✅ ${name}`);
}

const rules = (headline: string, industry: IndustryId) => checkCopy(copyWith(headline), industry).map((f) => f.ruleId);

test("업종 감지: 엄격한 업종 우선", () => {
  assert.equal(detectIndustry(biz("홍삼 건강기능식품 정기배송")), "health_food");
  assert.equal(detectIndustry(biz("강남 피부과 여드름 진료")), "medical");
  assert.equal(detectIndustry(biz("1인 피부관리실 예약")), "beauty");
  assert.equal(detectIndustry(biz("중등 수학 학원")), "academy");
  assert.equal(detectIndustry(biz("동네 베이커리 사전 주문")), "food");
  assert.equal(detectIndustry(biz("온라인 PT 코칭")), "general");
});

test("식품: 질병·면역 효능은 게시 불가", () => {
  assert.ok(rules("면역력 강화에 좋은 수제 생강청", "food").includes("food_disease"));
  assert.ok(rules("당뇨에 좋은 현미 도시락", "food").includes("food_disease"));
  assert.ok(!hasBlocking(checkCopy(copyWith("아침 7시에 굽는 동네 식빵"), "food")));
});

test("전문가 추천: 식품·건기식은 block, 일반은 warn", () => {
  const hf = checkCopy(copyWith("약사가 추천하는 유산균"), "health_food");
  assert.ok(hf.some((f) => f.ruleId === "expert_endorsement_regulated" && f.severity === "block"));
  const gen = checkCopy(copyWith("교수가 추천하는 글쓰기 강의"), "general");
  assert.ok(gen.some((f) => f.ruleId === "expert_endorsement" && f.severity === "warn"));
  assert.ok(!hasBlocking(gen));
});

test("의료: 안전 단정·치료경험담·과장은 block", () => {
  assert.ok(rules("부작용 없는 레이저 시술", "medical").includes("medical_safety"));
  assert.ok(rules("환자분들이 극찬한 도수치료", "medical").includes("testimonial_regulated"));
  assert.ok(rules("지역 1위 정형외과", "medical").includes("medical_superlative"));
});

test("학원·화장품·미용 업종 규칙", () => {
  assert.ok(rules("수능 1등급 보장 반", "academy").includes("academy_guarantee"));
  assert.ok(rules("아토피 치료 보습 크림", "cosmetics").includes("cosmetics_medical"));
  assert.deepEqual(rules("저자극 미백 크림", "cosmetics"), ["cosmetics_functional"]);
  assert.ok(rules("두피 치료 헤드스파", "beauty").includes("beauty_medical"));
});

test("공통: 최상급·보장·손님 체험담은 warn", () => {
  const f = checkCopy(copyWith("업계 최고 만족 보장", "직접 먹어봤는데 정말 맛있어요"), "general");
  assert.deepEqual([...new Set(f.map((x) => x.ruleId))].sort(), ["guarantee", "superlative", "testimonial"]);
  assert.ok(!hasBlocking(f));
});

test("평범한 카피는 지적 없음", () => {
  const f = checkCopy(copyWith("퇴근 후 30분, 작심삼일을 끝냅니다", "주 3회 화상 코칭으로 습관을 만듭니다."), "general");
  assert.equal(f.length, 0);
});

test("승인 검증: 승인·필수 항목·AI 표시 확인", () => {
  const clean = copyWith("중등 수학, 개념부터 다시 잡습니다");
  const base = { industry: "academy", ai_label: true, label_off_ack: false, disclosures: {}, approved: true };

  assert.equal(validateApproval(clean, null).ok, false);
  assert.equal(validateApproval(clean, parseApproval({ ...base, approved: false })).ok, false);

  const noDisc = validateApproval(clean, parseApproval(base));
  assert.ok(!noDisc.ok && noDisc.missing?.length === 2);

  const disclosures = { academy_reg_no: "제1234호", tuition: "월 30만 원" };
  assert.equal(validateApproval(clean, parseApproval({ ...base, disclosures, ai_label: false })).ok, false);

  const ok = validateApproval(clean, parseApproval({ ...base, disclosures }));
  assert.ok(ok.ok && ok.record.ai_label && ok.record.disclosures.tuition === "월 30만 원");

  const blocked = validateApproval(copyWith("합격 보장 특강"), parseApproval({ ...base, disclosures }));
  assert.ok(!blocked.ok && blocked.findings?.some((f) => f.severity === "block"));

  assert.equal(parseApproval({ ...base, industry: "casino" }), null);
});

test("규제 피드: 직렬화한 정규식이 원본과 같은 결과", () => {
  const feed = buildRulesFeed();
  assert.ok(feed.version && feed.rules.length === RULES.length);
  const samples = ["면역력 강화", "약사가 추천", "부작용 없는", "합격 보장", "업계 최고", "평범한 문장"];
  for (const r of feed.rules) {
    const original = RULES.find((x) => x.id === r.id)!;
    const revived = new RegExp(r.pattern, r.flags);
    for (const text of samples) assert.equal(revived.test(text), original.pattern.test(text), `${r.id}: ${text}`);
    if (r.industries !== "all") for (const id of r.industries) assert.ok(feed.industries.some((i) => i.id === id));
  }
  assert.ok(JSON.parse(JSON.stringify(feed)).rules[0].pattern);
});

console.log(`\n${passed}개 통과`);
