// lib/compliance/privacy.ts  [신규 — 컴플라이언스 P1]
// 공개 페이지 신청 폼의 개인정보 수집·이용 동의(개인정보보호법 제15조 제2항 고지 항목:
// 목적·항목·보유기간·거부권과 불이익). 문구를 바꾸면 LEAD_CONSENT_VERSION 을 올린다(리드에 버전이 남는다).

export const LEAD_CONSENT_VERSION = "2026-10-24";

export function leadConsentItems(operator: string): { label: string; value: string }[] {
  return [
    { label: "수집하는 곳", value: operator || "이 페이지 운영자" },
    { label: "수집 항목", value: "이메일 주소" },
    { label: "이용 목적", value: "신청 확인 및 관련 안내 연락" },
    { label: "보유 기간", value: "목적 달성 시 지체 없이 파기(최대 1년)" },
    { label: "동의 거부", value: "동의하지 않을 수 있으며, 이 경우 신청이 제한됩니다." },
  ];
}
