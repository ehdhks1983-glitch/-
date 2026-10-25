// lib/compliance/privacy.ts  [신규 — 컴플라이언스 P1]
// 공개 페이지 신청 폼의 개인정보 수집·이용 동의(개인정보보호법 제15조 제2항 고지 항목:
// 목적·항목·보유기간·거부권과 불이익). 외국인 손님용 페이지는 정보주체가 이해할 수 있도록 같은 내용을 번역해 보여 준다.
// 문구를 바꾸면 LEAD_CONSENT_VERSION 을 올린다(리드에 버전이 남는다).

import type { PageLang } from "@/lib/i18n/langs";

export const LEAD_CONSENT_VERSION = "2026-10-24";

interface ConsentText {
  label: string;
  required: string;
  rows: [collector: string, items: string, itemsValue: string, purpose: string, purposeValue: string, retention: string, retentionValue: string, refusal: string, refusalValue: string];
  fallbackOperator: string;
}

const CONSENT: Record<PageLang, ConsentText> = {
  ko: {
    label: "[필수] 개인정보 수집·이용에 동의합니다.",
    required: "개인정보 수집·이용에 동의해 주세요.",
    rows: ["수집하는 곳", "수집 항목", "이메일 주소", "이용 목적", "신청 확인 및 관련 안내 연락", "보유 기간", "목적 달성 시 지체 없이 파기(최대 1년)", "동의 거부", "동의하지 않을 수 있으며, 이 경우 신청이 제한됩니다."],
    fallbackOperator: "이 페이지 운영자",
  },
  en: {
    label: "[Required] I agree to the collection and use of my personal information.",
    required: "Please agree to the collection and use of your personal information.",
    rows: ["Collected by", "Items", "Email address", "Purpose", "Confirming your request and contacting you about it", "Retention", "Deleted without delay once the purpose is fulfilled (max. 1 year)", "Refusal", "You may decline, but you won't be able to submit the request."],
    fallbackOperator: "The operator of this page",
  },
  ja: {
    label: "[必須] 個人情報の収集・利用に同意します。",
    required: "個人情報の収集・利用に同意してください。",
    rows: ["収集者", "収集項目", "メールアドレス", "利用目的", "お申し込みの確認および関連するご連絡", "保有期間", "目的達成後、遅滞なく破棄（最長1年）", "同意の拒否", "同意しないこともできますが、その場合はお申し込みいただけません。"],
    fallbackOperator: "このページの運営者",
  },
  "zh-CN": {
    label: "[必填] 我同意收集和使用个人信息。",
    required: "请同意收集和使用个人信息。",
    rows: ["收集方", "收集项目", "电子邮箱", "使用目的", "确认申请及相关联系", "保存期限", "目的达成后立即销毁（最长1年）", "拒绝同意", "您可以不同意，但将无法提交申请。"],
    fallbackOperator: "本页面运营者",
  },
  "zh-TW": {
    label: "[必填] 我同意蒐集和使用個人資料。",
    required: "請同意蒐集和使用個人資料。",
    rows: ["蒐集方", "蒐集項目", "電子郵件", "使用目的", "確認申請及相關聯繫", "保存期限", "目的達成後立即銷毀（最長1年）", "拒絕同意", "您可以不同意，但將無法送出申請。"],
    fallbackOperator: "本頁面營運者",
  },
};

export function consentText(lang: PageLang = "ko"): { label: string; required: string } {
  const t = CONSENT[lang] ?? CONSENT.ko;
  return { label: t.label, required: t.required };
}

export function leadConsentItems(operator: string, lang: PageLang = "ko"): { label: string; value: string }[] {
  const t = CONSENT[lang] ?? CONSENT.ko;
  const [collector, items, itemsValue, purpose, purposeValue, retention, retentionValue, refusal, refusalValue] = t.rows;
  return [
    { label: collector, value: operator || t.fallbackOperator },
    { label: items, value: itemsValue },
    { label: purpose, value: purposeValue },
    { label: retention, value: retentionValue },
    { label: refusal, value: refusalValue },
  ];
}
