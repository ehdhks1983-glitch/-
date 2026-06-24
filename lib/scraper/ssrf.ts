// lib/scraper/ssrf.ts — SSRF 방어. 사용자가 준 URL을 서버가 fetch 하므로,
// 내부/사설/메타데이터 IP로의 요청을 차단한다(http/https만, DNS 해석 결과까지 검사).

import { lookup } from "node:dns/promises";
import net from "node:net";

function stripBrackets(host: string): string {
  return host.startsWith("[") && host.endsWith("]") ? host.slice(1, -1) : host;
}

/** IPv4 사설/루프백/링크로컬/메타데이터/CGNAT 등 차단 대상 여부. */
function isPrivateV4(ip: string): boolean {
  const p = ip.split(".").map(Number);
  if (p.length !== 4 || p.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return true; // 이상치 → 차단
  const [a, b] = p;
  if (a === 10) return true; // 10/8
  if (a === 127) return true; // loopback
  if (a === 0) return true; // 0/8
  if (a === 169 && b === 254) return true; // link-local + 169.254.169.254 메타데이터
  if (a === 172 && b >= 16 && b <= 31) return true; // 172.16/12
  if (a === 192 && b === 168) return true; // 192.168/16
  if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT 100.64/10
  if (a >= 224) return true; // multicast/reserved
  return false;
}

function isPrivateV6(ip: string): boolean {
  const x = ip.toLowerCase();
  if (x === "::1" || x === "::") return true; // loopback / unspecified
  if (x.startsWith("fc") || x.startsWith("fd")) return true; // ULA fc00::/7
  if (x.startsWith("fe8") || x.startsWith("fe9") || x.startsWith("fea") || x.startsWith("feb")) return true; // link-local fe80::/10
  const mapped = x.match(/::ffff:(\d+\.\d+\.\d+\.\d+)$/); // v4-mapped
  if (mapped) return isPrivateV4(mapped[1]);
  return false;
}

function isPrivateIp(ip: string): boolean {
  const v = net.isIP(ip);
  if (v === 4) return isPrivateV4(ip);
  if (v === 6) return isPrivateV6(ip);
  return true; // IP 아님 → 보수적으로 차단
}

/** 공개 URL인지 검증. 내부/사설/메타데이터로 향하면 throw. (각 redirect hop마다 호출) */
export async function assertPublicUrl(rawUrl: string): Promise<void> {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    throw new Error("잘못된 URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error(`차단된 프로토콜: ${url.protocol}`);

  const host = stripBrackets(url.hostname).toLowerCase();
  if (!host || host === "localhost" || host.endsWith(".local") || host.endsWith(".internal") || host === "metadata.google.internal") {
    throw new Error(`차단된 호스트: ${host}`);
  }

  let addresses: string[];
  if (net.isIP(host)) {
    addresses = [host];
  } else {
    try {
      const res = await lookup(host, { all: true });
      addresses = res.map((r) => r.address);
    } catch {
      throw new Error(`DNS 해석 실패: ${host}`);
    }
    if (addresses.length === 0) throw new Error(`주소 없음: ${host}`);
  }
  for (const a of addresses) {
    if (isPrivateIp(a)) throw new Error(`내부/사설 IP 차단: ${host} → ${a}`);
  }
}
