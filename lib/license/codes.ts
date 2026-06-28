// lib/license/codes.ts  [신규]
// 라이선스 코드 생성/정규화. 서버 전용(node:crypto 의존).
// 형식: ALLB-XXXXX-XXXXX-XXXXX (혼동 문자 제외 32자 알파벳, 암호학적 난수).

import { randomInt } from "node:crypto";
import { CODE_ALPHABET, CODE_GROUPS, CODE_GROUP_LEN, CODE_PREFIX } from "./config";

/** 새 라이선스 코드 1개 생성(정식 형식, 대시 포함). */
export function generateCode(): string {
  const groups: string[] = [];
  for (let g = 0; g < CODE_GROUPS; g++) {
    let s = "";
    for (let i = 0; i < CODE_GROUP_LEN; i++) {
      s += CODE_ALPHABET[randomInt(0, CODE_ALPHABET.length)];
    }
    groups.push(s);
  }
  return [CODE_PREFIX, ...groups].join("-");
}

/**
 * 입력 코드를 정식 형식으로 정규화.
 * 대소문자/공백/대시 차이를 흡수하고, 알파벳 외 문자가 섞이면 null.
 * 사용자가 대시 없이 붙여넣어도(ALLBXXXXX...) 동일하게 매칭된다.
 */
export function normalizeCode(input: string): string | null {
  const cleaned = (input ?? "").toUpperCase().replace(/[\s-]+/g, "");
  if (!cleaned.startsWith(CODE_PREFIX)) return null;
  const body = cleaned.slice(CODE_PREFIX.length);
  const expectedLen = CODE_GROUPS * CODE_GROUP_LEN;
  if (body.length !== expectedLen) return null;
  // 본문 문자가 전부 허용 알파벳인지 확인.
  for (const ch of body) {
    if (!CODE_ALPHABET.includes(ch)) return null;
  }
  const groups: string[] = [];
  for (let g = 0; g < CODE_GROUPS; g++) {
    groups.push(body.slice(g * CODE_GROUP_LEN, (g + 1) * CODE_GROUP_LEN));
  }
  return [CODE_PREFIX, ...groups].join("-");
}
