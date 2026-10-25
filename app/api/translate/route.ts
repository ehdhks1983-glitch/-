// app/api/translate/route.ts  [신규 — P2 외국인 손님 패키지]
// 원문 카피 → 외국인 손님용 번역본(요청한 언어들, 병렬). 실패한 언어는 failed 로 알려 주고 나머지는 돌려준다.

import { NextResponse } from "next/server";
import { translateCopy } from "@/lib/ai/translateCopy";
import { FOREIGN_LANGS, isForeignLang, type ForeignLang, type Translations } from "@/lib/i18n/langs";
import { sanitizeCopy, sanitizeText } from "@/lib/sanitize";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const maxDuration = 60;

const TRANSLATE_LIMIT = 6; // 분당 요청(IP 기준) — 요청 1번에 모델 호출이 최대 4번
const TRANSLATE_WINDOW_MS = 60_000;

export async function POST(req: Request) {
  sweep();
  if (!rateLimit(clientKey(req, "translate"), TRANSLATE_LIMIT, TRANSLATE_WINDOW_MS).ok) {
    return NextResponse.json({ error: "요청이 많아요. 잠시 후 다시 시도해 주세요." }, { status: 429 });
  }

  const body = (await req.json().catch(() => null)) as Record<string, unknown> | null;
  const copy = body?.copy ? sanitizeCopy(body.copy as never) : null;
  if (!copy || !copy.hero.headline) return NextResponse.json({ error: "번역할 페이지 내용이 없어요." }, { status: 400 });

  const requested = Array.isArray(body?.langs) ? (body!.langs as unknown[]).filter(isForeignLang) : [...FOREIGN_LANGS];
  const langs = [...new Set(requested)] as ForeignLang[];
  if (langs.length === 0) return NextResponse.json({ error: "번역할 언어를 골라 주세요." }, { status: 400 });

  const ctx = { serviceName: sanitizeText(body?.service_name, 60), hours: sanitizeText(body?.hours, 120) };
  const results = await Promise.allSettled(langs.map((lang) => translateCopy(copy, lang, ctx)));

  const translations: Translations = {};
  const failed: ForeignLang[] = [];
  results.forEach((r, i) => {
    if (r.status === "fulfilled") translations[langs[i]] = r.value;
    else {
      failed.push(langs[i]);
      console.error(`[api/translate] ${langs[i]} 실패:`, r.reason);
    }
  });
  if (failed.length === langs.length) {
    return NextResponse.json({ error: "번역 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요." }, { status: 502 });
  }
  return NextResponse.json({ translations, failed });
}
