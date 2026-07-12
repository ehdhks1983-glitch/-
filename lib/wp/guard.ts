// lib/wp/guard.ts  [신규 — 워드프레스 자동 발행] ※ 서버 전용(node:dns 사용)
// 사용자가 입력한 사이트 주소로 서버가 대신 요청하는 구조(프록시)의 SSRF 방어.
// 규칙: https 만 허용 + 내부/사설 대역 호스트 차단(리터럴 검사 + DNS 조회 검사).
// 한계: DNS 리바인딩까지 완전 차단하진 않는다(요청 직전 재조회) — README 보안 절 참고.

import { lookup } from "node:dns/promises";

/** 주소 검증 실패 — 사용자에게 그대로 보여줄 수 있는 한국어 메시지를 담는다. */
export class WpGuardError extends Error {}

const MAX_URL_LEN = 300;

/**
 * 입력 주소를 정규화한다: 스킴 보정 → https 강제 → origin+경로만 남기고 말단 슬래시 제거.
 * 예) "example.com/blog/" → "https://example.com/blog"
 */
export function normalizeSiteUrl(raw: string): string {
  const input = (raw || "").trim();
  if (!input) throw new WpGuardError("사이트 주소를 입력해 주세요.");
  if (input.length > MAX_URL_LEN) throw new WpGuardError("사이트 주소가 너무 깁니다.");

  const withScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(input) ? input : `https://${input}`;

  let u: URL;
  try {
    u = new URL(withScheme);
  } catch {
    throw new WpGuardError("사이트 주소 형식이 올바르지 않습니다. 예: https://example.com");
  }

  if (u.protocol !== "https:") {
    throw new WpGuardError(
      "https 주소만 사용할 수 있어요. (워드프레스 응용 프로그램 비밀번호도 https를 요구합니다)",
    );
  }
  if (!u.hostname) throw new WpGuardError("사이트 주소에 도메인이 없습니다.");
  if (u.username || u.password) throw new WpGuardError("주소에 아이디/비밀번호를 넣을 수 없어요.");

  const path = u.pathname.replace(/\/+$/, "");
  return `${u.origin}${path}`;
}

/** 도메인 이름 자체로 거르는 1차 필터(내부망 관용 도메인) */
function isForbiddenHostname(hostname: string): boolean {
  const h = hostname.toLowerCase();
  if (h === "localhost" || h.endsWith(".localhost")) return true;
  if (h.endsWith(".local") || h.endsWith(".internal") || h.endsWith(".lan")) return true;
  return false;
}

/** IPv4 사설/예약 대역 검사 */
function isPrivateIPv4(ip: string): boolean {
  const parts = ip.split(".").map(Number);
  if (parts.length !== 4 || parts.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) {
    return true; // 형식 이상 = 차단
  }
  const [a, b, c] = parts;
  if (a === 0 || a === 10 || a === 127) return true;
  if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
  if (a === 169 && b === 254) return true; // link-local (클라우드 메타데이터 포함)
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 0 && (c === 0 || c === 2)) return true;
  if (a === 192 && b === 168) return true;
  if (a === 198 && (b === 18 || b === 19)) return true;
  if (a === 198 && b === 51 && c === 100) return true;
  if (a === 203 && b === 0 && c === 113) return true;
  if (a >= 224) return true; // 멀티캐스트/예약/브로드캐스트
  return false;
}

/** IPv6 사설/예약 대역 검사(일반 표기 기준) */
function isPrivateIPv6(ip: string): boolean {
  const h = ip.toLowerCase();
  if (h === "::" || h === "::1") return true;
  if (h.startsWith("fc") || h.startsWith("fd")) return true; // ULA fc00::/7
  if (h.startsWith("fe8") || h.startsWith("fe9") || h.startsWith("fea") || h.startsWith("feb")) {
    return true; // link-local fe80::/10
  }
  if (h.startsWith("ff")) return true; // 멀티캐스트
  const mapped = h.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/); // IPv4-mapped
  if (mapped) return isPrivateIPv4(mapped[1]);
  return false;
}

function isPrivateIp(ip: string): boolean {
  return ip.includes(":") ? isPrivateIPv6(ip) : isPrivateIPv4(ip);
}

/**
 * 정규화된 사이트 주소가 공개 인터넷 호스트인지 확인한다.
 * IP 리터럴은 즉시 검사, 도메인은 DNS로 풀어 모든 결과 IP를 검사한다. 위반 시 WpGuardError.
 */
export async function assertPublicSiteUrl(siteUrl: string): Promise<void> {
  const u = new URL(siteUrl);
  const host = u.hostname;

  if (isForbiddenHostname(host)) {
    throw new WpGuardError("내부망 주소로는 연결할 수 없어요. 공개된 사이트 주소를 입력해 주세요.");
  }

  const isIpLiteral = /^\d+\.\d+\.\d+\.\d+$/.test(host) || host.includes(":");
  if (isIpLiteral) {
    if (isPrivateIp(host)) {
      throw new WpGuardError("내부망 IP로는 연결할 수 없어요. 공개된 사이트 주소를 입력해 주세요.");
    }
    return;
  }

  let addrs: { address: string }[];
  try {
    addrs = await lookup(host, { all: true, verbatim: true });
  } catch {
    throw new WpGuardError("도메인을 찾을 수 없어요. 사이트 주소를 다시 확인해 주세요.");
  }
  if (addrs.length === 0) {
    throw new WpGuardError("도메인을 찾을 수 없어요. 사이트 주소를 다시 확인해 주세요.");
  }
  for (const { address } of addrs) {
    if (isPrivateIp(address)) {
      throw new WpGuardError("내부망을 가리키는 주소로는 연결할 수 없어요.");
    }
  }
}
