// lib/i18n/ui.ts  [신규 — P2 외국인 손님 패키지]
// 공개 페이지의 고정 문구(템플릿 라벨·신청 폼·매장 안내) 5개 언어. 생성 카피가 아니라 화면 틀의 글자다.

import type { PageLang } from "./langs";

interface UiText {
  template: {
    faq: string;
    features: string;
    free: string;
    badge: string;
    why: string;
    spots: string;
    process: string;
    consult: string;
    waitlistBrand: string;
    agencyBrand: string;
  };
  signup: {
    headline: string;
    sub: string;
    email: string;
    submit: string;
    submitting: string;
    done: string;
    failed: string;
  };
  place: { title: string; address: string; phone: string; hours: string; naverMap: string; googleMap: string };
  language: string;
}

const UI: Record<PageLang, UiText> = {
  ko: {
    template: {
      faq: "자주 묻는 질문",
      features: "핵심 기능",
      free: "부담 없이 시작하세요",
      badge: "곧 출시",
      why: "왜 지금인가",
      spots: "사전 등록자에게 가장 먼저 알려드려요",
      process: "진행 방식",
      consult: "부담 없는 상담부터",
      waitlistBrand: "사전등록",
      agencyBrand: "에이전시",
    },
    signup: {
      headline: "지금 신청하세요",
      sub: "이메일을 남기면 가장 먼저 알려드릴게요.",
      email: "이메일 주소",
      submit: "신청하기",
      submitting: "신청 중…",
      done: "신청이 접수됐어요. 곧 연락드릴게요! 🎉",
      failed: "신청에 실패했어요. 잠시 후 다시 시도해 주세요.",
    },
    place: { title: "매장 안내", address: "주소", phone: "전화", hours: "영업시간", naverMap: "네이버 지도", googleMap: "구글 지도" },
    language: "언어",
  },
  en: {
    template: {
      faq: "FAQ",
      features: "Features",
      free: "No credit card required",
      badge: "Coming soon",
      why: "Why join",
      spots: "Early access — limited spots",
      process: "How we work",
      consult: "Free consultation",
      waitlistBrand: "Waitlist",
      agencyBrand: "Agency",
    },
    signup: {
      headline: "Sign up now",
      sub: "Leave your email and we'll let you know first.",
      email: "Email address",
      submit: "Sign up",
      submitting: "Sending…",
      done: "Thanks! We'll be in touch soon. 🎉",
      failed: "Something went wrong. Please try again in a moment.",
    },
    place: { title: "Visit us", address: "Address", phone: "Phone", hours: "Hours", naverMap: "Naver Map", googleMap: "Google Maps" },
    language: "Language",
  },
  ja: {
    template: {
      faq: "よくある質問",
      features: "特徴",
      free: "お気軽に始めてください",
      badge: "まもなく公開",
      why: "今参加する理由",
      spots: "事前登録の方にいち早くお知らせします",
      process: "進め方",
      consult: "お気軽にご相談ください",
      waitlistBrand: "事前登録",
      agencyBrand: "エージェンシー",
    },
    signup: {
      headline: "今すぐお申し込み",
      sub: "メールアドレスを残していただければ、いち早くお知らせします。",
      email: "メールアドレス",
      submit: "申し込む",
      submitting: "送信中…",
      done: "お申し込みを受け付けました。まもなくご連絡します！🎉",
      failed: "送信できませんでした。しばらくしてからもう一度お試しください。",
    },
    place: { title: "店舗情報", address: "住所", phone: "電話", hours: "営業時間", naverMap: "NAVER地図", googleMap: "Googleマップ" },
    language: "言語",
  },
  "zh-CN": {
    template: {
      faq: "常见问题",
      features: "主要特点",
      free: "轻松开始",
      badge: "即将推出",
      why: "为什么现在加入",
      spots: "预先登记者将第一时间收到通知",
      process: "服务流程",
      consult: "欢迎咨询",
      waitlistBrand: "预先登记",
      agencyBrand: "代理服务",
    },
    signup: {
      headline: "立即申请",
      sub: "留下邮箱，我们会第一时间通知您。",
      email: "电子邮箱",
      submit: "提交",
      submitting: "提交中…",
      done: "已收到您的申请，我们会尽快联系您！🎉",
      failed: "提交失败，请稍后再试。",
    },
    place: { title: "店铺信息", address: "地址", phone: "电话", hours: "营业时间", naverMap: "Naver地图", googleMap: "谷歌地图" },
    language: "语言",
  },
  "zh-TW": {
    template: {
      faq: "常見問題",
      features: "主要特色",
      free: "輕鬆開始",
      badge: "即將推出",
      why: "為什麼現在加入",
      spots: "預先登記者將第一時間收到通知",
      process: "服務流程",
      consult: "歡迎諮詢",
      waitlistBrand: "預先登記",
      agencyBrand: "代理服務",
    },
    signup: {
      headline: "立即申請",
      sub: "留下電子郵件，我們會第一時間通知您。",
      email: "電子郵件",
      submit: "送出",
      submitting: "送出中…",
      done: "已收到您的申請，我們會盡快聯繫您！🎉",
      failed: "送出失敗，請稍後再試。",
    },
    place: { title: "店鋪資訊", address: "地址", phone: "電話", hours: "營業時間", naverMap: "Naver地圖", googleMap: "Google地圖" },
    language: "語言",
  },
};

export function uiText(lang: PageLang | undefined): UiText {
  return UI[lang ?? "ko"] ?? UI.ko;
}
