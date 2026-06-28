// lib/license/config.ts  [신규]
// 통합 라이선스(올인원) 설정. "코드 1개로 6개 봇 전부" 모델.
// - 봇 목록: 분석/표시용 메타. 코드는 봇을 가리지 않고 전부 잠금 해제한다.
//   (검증 요청의 bot_id 는 어떤 봇이 호출했는지 로그/통계 용도로만 쓴다.)
// - 봇 id/이름은 env(LICENSE_BOTS)로 덮어쓸 수 있다: "id:이름,id:이름,...".

export interface BotMeta {
  id: string;
  name: string;
}

const DEFAULT_BOTS: BotMeta[] = [
  { id: "bot1", name: "봇 1" },
  { id: "bot2", name: "봇 2" },
  { id: "bot3", name: "봇 3" },
  { id: "bot4", name: "봇 4" },
  { id: "bot5", name: "봇 5" },
  { id: "bot6", name: "봇 6" },
];

/** 통합 라이선스가 잠금 해제하는 봇 목록. env(LICENSE_BOTS)로 덮어쓰기 가능. */
export function bots(): BotMeta[] {
  const raw = (process.env.LICENSE_BOTS ?? "").trim();
  if (!raw) return DEFAULT_BOTS;
  const parsed = raw
    .split(",")
    .map((pair) => pair.trim())
    .filter(Boolean)
    .map((pair) => {
      const [id, ...rest] = pair.split(":");
      const cleanId = (id ?? "").trim();
      const name = rest.join(":").trim() || cleanId;
      return cleanId ? { id: cleanId, name } : null;
    })
    .filter((b): b is BotMeta => b !== null);
  return parsed.length > 0 ? parsed : DEFAULT_BOTS;
}

/** 검증 요청의 bot_id 가 등록된 봇인지(로그 정합성용). 미등록도 검증 자체는 막지 않는다. */
export function isKnownBot(botId: string): boolean {
  return bots().some((b) => b.id === botId);
}

// ── 코드 포맷 ──
// 사람이 부르기 쉬운 그룹형. 혼동 문자(0/O/1/I) 제외한 32자 알파벳.
export const CODE_PREFIX = "ALLB"; // All-Bots
export const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
export const CODE_GROUPS = 3; // 접두사 뒤 그룹 수
export const CODE_GROUP_LEN = 5; // 각 그룹 길이

// ── 검증 결과 사유 코드(봇이 분기에 사용) ──
export const VERIFY_REASONS = {
  ok: "ok",
  notFound: "not_found",
  revoked: "revoked",
  inactive: "inactive",
  expired: "expired",
  deviceLimit: "device_limit",
} as const;

export type VerifyReason = (typeof VERIFY_REASONS)[keyof typeof VERIFY_REASONS];
