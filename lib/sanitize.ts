// lib/sanitize.ts
// 사용자 입력 텍스트 정화. React 는 문자열 children 을 기본 이스케이프하므로(XSS 안전),
// 여기서는 추가 방어로 HTML 태그·제어문자 제거 + 길이 제한을 한 번 더 적용한다.
// 규칙: 사용자 입력을 절대 dangerouslySetInnerHTML 에 넣지 않는다.

/** C0 제어문자/DEL 제거(탭 0x09·개행 0x0A·CR 0x0D 은 보존). 코드포인트로 판별. */
function stripControlChars(input: string): string {
  let out = "";
  for (const ch of input) {
    const code = ch.codePointAt(0) ?? 0;
    const isControl = (code <= 0x1f && code !== 0x09 && code !== 0x0a && code !== 0x0d) || code === 0x7f;
    if (!isControl) out += ch;
  }
  return out;
}

/** 단일 문자열 정화: 태그/제어문자 제거 + 트림 + 길이 제한. */
export function sanitizeText(input: unknown, maxLen = 2000): string {
  if (typeof input !== "string") return "";
  let s = stripControlChars(input.replace(/<[^>]*>/g, "")).trim();
  if (s.length > maxLen) s = s.slice(0, maxLen).trimEnd();
  return s;
}
