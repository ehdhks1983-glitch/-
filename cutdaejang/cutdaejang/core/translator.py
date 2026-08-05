"""🌏 자막 마무리 손질 (v1.45 목록 88·89) — 렌더 직전 스펙 후처리.

두 가지를 여기서 한 번에 한다 (편집·생성 두 렌더 길목이 같이 부른다):
  ① 병기 번역 — 한국어 자막 아래 영어/일본어/중국어 한 줄 (제미나이 일괄 1콜)
  ② 강조색 스위치 — «강조색 자동»을 끄면 AI가 고른 강조 단어 색을 뺀다
     (회원님이 «»로 직접 칠한 색은 건드리지 않는다 — 89번 결정)

렌더(ass_writer)는 설정을 모르는 순수 함수로 유지한다 — 설정을 읽어 스펙에
새기는 일은 전부 여기서 끝낸다.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .. import config

log = logging.getLogger("cutdaejang")

LANGS = {"en": "영어", "ja": "일본어", "zh": "중국어(간체)"}
_LANG_PROMPT_NAME = {"en": "자연스러운 영어", "ja": "자연스러운 일본어",
                     "zh": "자연스러운 중국어(간체)"}

TRANS_PROMPT = """\
역할: 쇼츠 자막 번역가
아래 한국어 자막을 {lang}로 번역해줘. 화면 아래 작게 병기되는 줄이다.
규칙:
- 줄 수와 순서는 절대 그대로 (입력 {n}줄 → 출력 정확히 {n}줄, 1:1 대응)
- 자막 말투: 짧고 구어체. 설명 덧붙이기 금지
- 숫자·단위·고유명사·브랜드 이름은 그대로
- 번역이 곤란한 줄은 빈 문자열 ""
입력 자막:
{lines}
출력(JSON만): {{"lines":["번역 1줄","번역 2줄", ...]}}
"""


def translate_lines(texts: list, lang: str, model: str = "gemini-2.5-flash",
                    api_key=None) -> list:
    """자막 줄들을 일괄 번역 — 줄 수 보존, 어긋난 줄은 ""(병기 생략).

    refine_subtitles(script_generator)와 같은 구조·같은 전송로(_post_ai)를 쓴다.
    """
    from .script_generator import ScriptError, _as_dict, _as_list, _post_ai  # noqa: PLC0415

    if lang not in LANGS:
        raise ScriptError(f"지원하지 않는 병기 언어: {lang!r}")
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("제미나이 키가 없어 병기 번역을 쓸 수 없습니다 (🔑 API 연동)")
    # «강조» 표식은 번역에 방해만 된다 — 뜻만 넘긴다
    src = [re.sub(r"[«»]", "", str(t or "")) for t in texts]
    numbered = "\n".join(f"{i + 1}) {t}" for i, t in enumerate(src))
    prompt = TRANS_PROMPT.format(lang=_LANG_PROMPT_NAME[lang], n=len(src),
                                 lines=numbered)
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _post_ai(url, payload, key, timeout=60.0)
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"번역 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    lines = _as_list(_as_dict(json.loads(cleaned)).get("lines"))
    out = []
    for i in range(len(src)):
        cand = str(lines[i]).strip() if i < len(lines) else ""
        out.append("" if cand == src[i] else cand)   # 번역이 원문 그대로면 병기 무의미
    return out


def finalize(spec) -> str:
    """렌더 직전 스펙 후처리 — 반환값은 로그에 남길 안내 한 줄 (없으면 "").

    실패해도 절대 렌더를 막지 않는다: 번역이 안 되면 병기만 빠진 영상이 나온다.
    """
    notes = []
    try:
        sub_cfg = (config.load_settings().get("subtitle") or {})
    except Exception:  # noqa: BLE001 — 설정을 못 읽어도 렌더는 계속
        sub_cfg = {}

    # ② 강조색 자동 스위치 (89) — 끄면 AI가 고른 강조 단어를 지운다.
    #    «»로 직접 칠한 수동 마크업은 문장 텍스트라 여기 안 걸린다.
    if sub_cfg.get("highlight_on") is False:
        n = 0
        for s in getattr(spec, "subtitles", []) or []:
            if getattr(s, "highlight", ""):
                s.highlight = ""
                n += 1
        if n:
            notes.append(f"🎨 강조색 자동 끔 — AI 강조 단어 {n}곳 색 뺌")

    # ① 병기 번역 (88)
    lang = str(sub_cfg.get("sub_lang") or "")
    subs = [s for s in (getattr(spec, "subtitles", []) or [])
            if str(getattr(s, "text", "")).strip()]
    if lang in LANGS and subs:
        try:
            tr = translate_lines([s.text for s in subs], lang)
            n = 0
            for s, t in zip(subs, tr):
                if t:
                    s.trans = t
                    n += 1
            if n:
                spec.style.sub_lang = lang     # 렌더가 병기 글씨체를 고르는 근거
                notes.append(f"🌏 {LANGS[lang]} 병기 자막 {n}줄 넣음 (제미나이 1회)")
            else:
                notes.append("🌏 병기 번역 결과가 비어 이번엔 뺐어요")
        except Exception as e:  # noqa: BLE001 — 키 없음·네트워크·형식 전부
            notes.append(f"🌏 병기 번역 생략 — {e}")

    for m in notes:
        log.info(m)
    return " · ".join(notes)
