"""주제 → 구조화 JSON 대본 (기획안 §5.1, 부록 A 프롬프트).

숫자·영어 약어를 한글 발음으로 표기하도록 프롬프트에서 강제한다(TTS 오독 방지, §7-6).
JSON 파싱 실패 시 예외를 던지고, 자동 모드의 1회 재생성 정책은 오케스트레이터가 담당한다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .tts_engine import _http_post_json


class ScriptError(RuntimeError):
    pass


class ScriptParseError(ScriptError):
    """모델 응답이 유효한 대본 JSON이 아님 (자동 모드: 1회 재생성 대상)."""


PROMPT_TEMPLATE = """\
역할: 유튜브 쇼츠 대본 작가
입력: 주제="{topic}", 톤="{tone}", 목표길이={target_sec}초
규칙:
- 첫 문장은 3초 안에 시선을 잡는 훅 / 마지막 문장은 CTA
- 문장당 반드시 {max_chars}자 이내 (자막 1줄). 초과 문장 금지 — 길면 두 문장으로 나눌 것
- 구어체. 숫자·영어 약어는 한글 발음으로 표기 (TTS 오독 방지. 예: "2026년"→"이천이십육년", "AI"→"에이아이")
- highlight: 각 문장에서 시청자가 기억해야 할 단어 1개 (문장에 그대로 포함된 단어, 없으면 빈 문자열)
출력(JSON만): {{"title":"","sentences":[{{"text":"","highlight":""}},...],"background_prompt":"","hashtags":[""]}}
"""


@dataclass
class Script:
    title: str
    sentences: List[str]
    highlights: List[str] = field(default_factory=list)  # 문장별 강조 단어 (병렬 리스트)
    background_prompt: str = ""
    hashtags: List[str] = field(default_factory=list)

    def __post_init__(self):
        # highlights는 항상 sentences와 같은 길이로 정규화
        self.highlights = (self.highlights or [])[: len(self.sentences)]
        self.highlights += [""] * (len(self.sentences) - len(self.highlights))

    @classmethod
    def from_json_text(cls, text: str) -> "Script":
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ScriptParseError(f"대본 JSON 파싱 실패: {e}\n원문 앞부분: {cleaned[:200]}") from e
        raw = data.get("sentences")
        if not isinstance(raw, list) or not raw:
            raise ScriptParseError(f"sentences 형식 오류: {raw!r}")

        sentences, highlights = [], []
        for item in raw:
            if isinstance(item, str) and item.strip():  # 구버전 문자열 형식 호환
                sentences.append(item.strip())
                highlights.append("")
            elif isinstance(item, dict) and str(item.get("text", "")).strip():
                sentences.append(str(item["text"]).strip())
                highlights.append(str(item.get("highlight", "") or "").strip())
            else:
                raise ScriptParseError(f"sentences 항목 형식 오류: {item!r}")
        # 리스트 병렬 형식({"sentences":[...], "highlights":[...]})도 수용
        if not any(highlights) and isinstance(data.get("highlights"), list):
            highlights = [str(h or "").strip() for h in data["highlights"]]

        return cls(
            title=str(data.get("title", "")),
            sentences=sentences,
            highlights=highlights,
            background_prompt=str(data.get("background_prompt", "")),
            hashtags=[str(h) for h in data.get("hashtags", []) if h],
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "sentences": [
                    {"text": t, "highlight": h}
                    for t, h in zip(self.sentences, self.highlights)
                ],
                "background_prompt": self.background_prompt,
                "hashtags": self.hashtags,
            },
            ensure_ascii=False,
            indent=2,
        )


class GeminiScript:
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise ScriptError("GEMINI_API_KEY가 설정되어 있지 않습니다")

    def generate(
        self, topic: str, tone: str = "정보형", target_sec: int = 60, max_chars: int = 22
    ) -> Script:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": PROMPT_TEMPLATE.format(
                                topic=topic, tone=tone, target_sec=target_sec, max_chars=max_chars
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        data = _http_post_json(url, payload, {"x-goog-api-key": self.api_key})
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ScriptError(f"Gemini 응답 형식 예상 밖: {json.dumps(data)[:300]}") from e
        return Script.from_json_text(text)


HOOK_PROMPT = """\
역할: 유튜브 쇼츠/영상 썸네일 카피라이터
주제/내용: "{context}"
위 내용으로 시선을 확 잡는 **후킹 제목** {n}개를 지어줘.
규칙:
- 각 제목은 1~2줄, 짧고 강하게 (궁금증·숫자·반전·이득 중 하나 활용)
- 낚시성 과장 금지, 내용과 관련
- 출력은 제목만, 한 줄에 하나씩 (번호·따옴표·설명 없이)
"""


def suggest_hooks(context: str, n: int = 5, model: str = "gemini-2.5-flash",
                  api_key=None) -> list:
    """Gemini로 후킹 제목 후보 n개 생성. 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 제목 추천을 쓸 수 없습니다")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {"contents": [{"parts": [{"text": HOOK_PROMPT.format(context=context, n=n)}]}]}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"제목 추천 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    hooks = []
    for line in text.splitlines():
        line = re.sub(r'^\s*(?:\d+[.)]\s*|[-*•]\s*|["\'])|["\']\s*$', "", line).strip()
        if line and len(line) <= 40:
            hooks.append(line)
    return hooks[:n]


HIGHLIGHT_PROMPT = """\
역할: 유튜브 쇼츠 편집자
아래는 긴 영상의 자막 목록이야. 각 줄 앞의 번호와 (길이)를 참고해.
목표: 이 중에서 **가장 임팩트 있고 그 자체로 말이 되는** 자막만 골라 합치면
약 {target}초짜리 쇼츠가 되게 해. 핵심만 짧고 굵게. 지루한 설명·군더더기는 버려.
가능하면 도입 훅 → 핵심 → 마무리 흐름이 되도록.
자막들:
{lines}
출력(JSON만): {{"keep":[고른 번호들], "reason":"왜 이렇게 골랐는지 한 줄"}}
"""


def _fmt_sub_lines(subs: list) -> str:
    out = []
    for i, s in enumerate(subs):
        sec = max(0.1, (s.get("end_us", 0) - s.get("start_us", 0)) / 1e6)
        out.append(f"{i}) ({sec:.1f}초) {s.get('text','')}")
    return "\n".join(out)


def suggest_highlights(subs: list, target_sec: int = 30,
                       model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """자막 목록 → 쇼츠용 핵심 자막 번호 골라주기 (Gemini). 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 핵심 추천을 쓸 수 없습니다")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    prompt = HIGHLIGHT_PROMPT.format(target=target_sec, lines=_fmt_sub_lines(subs))
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"핵심 추천 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    obj = json.loads(cleaned)
    keep = [int(i) for i in obj.get("keep", []) if 0 <= int(i) < len(subs)]
    return {"keep": sorted(set(keep)), "reason": str(obj.get("reason", ""))}


REFINE_PROMPT = """\
역할: 유튜브 자막 교정 편집자
아래는 음성 인식(STT)으로 받아쓴 자막이라, 발음·잡음 때문에 잘못 적힌 부분이 있을 수 있어.
각 줄을 자연스럽고 말이 되는 한국어로 고쳐줘.{ctx}
규칙:
- 줄 수와 순서는 절대 그대로 (입력 {n}줄 → 출력 정확히 {n}줄, 1:1 대응)
- 명백한 오인식만 문맥에 맞게 자연스럽게 교정. 없는 내용을 지어내지 마.
- 구어체 유지, 자막용이라 한 줄은 짧고 간결하게
- 도무지 못 고치겠는 줄은 원문 그대로 둬
입력 자막:
{lines}
출력(JSON만): {{"lines":["교정된 1줄","교정된 2줄", ...]}}
"""


def refine_subtitles(texts: list, context: str = "",
                     model: str = "gemini-2.5-flash", api_key=None) -> list:
    """STT 자막을 문맥 기반으로 자연스럽게 교정 (발음 오인식 자동 수정). 키 없으면 ScriptError.

    줄 수·순서는 보존한다. 응답이 어긋나면 해당 줄은 원문을 유지.
    """
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 대본 다듬기를 쓸 수 없습니다")
    src = [str(t or "") for t in texts]
    numbered = "\n".join(f"{i + 1}) {t}" for i, t in enumerate(src))
    ctx = f'\n영상 주제/맥락: "{context.strip()}" (교정에 참고)' if context.strip() else ""
    prompt = REFINE_PROMPT.format(n=len(src), lines=numbered, ctx=ctx)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"대본 다듬기 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    obj = json.loads(cleaned)
    lines = obj.get("lines") or []
    # 줄 수가 어긋나면 있는 만큼만 교체, 나머지는 원문 유지
    out = []
    for i, orig in enumerate(src):
        cand = str(lines[i]).strip() if i < len(lines) else ""
        out.append(cand if cand else orig)
    return out


# 후킹 신호 키워드 — 쇼츠에서 시선을 잡는 표현들
_HOOK_WORDS = (
    "왜", "어떻게", "비법", "꿀팁", "충격", "진짜", "무료", "방법", "핵심", "주의",
    "실수", "비밀", "최고", "제일", "공개", "후기", "추천", "정리", "결론", "반전",
    "이것만", "하지 마", "안 됩니다", "됩니다", "만에", "단 ",
)


def _hook_score(text: str, dur: float, idx: int, total: int) -> float:
    """자막 한 줄의 '후킹 점수' — 숫자·질문·키워드·정보밀도·위치 보정."""
    t = text.strip()
    score = min(len(t) / max(dur, 0.5), 8.0)          # 정보 밀도 (상한)
    if re.search(r"\d", t):
        score += 3.0                                   # 숫자 = 썸네일급 훅
    if "?" in t:
        score += 2.5                                   # 궁금증 유발
    if "!" in t:
        score += 1.5
    score += sum(1.5 for w in _HOOK_WORDS if w in t)
    if idx == 0:
        score += 2.0                                   # 도입부(첫 마디) 보정
    if total > 2 and idx == total - 1:
        score += 1.0                                   # 마무리(결론) 소폭 보정
    return score


def suggest_highlights_heuristic(subs: list, target_sec: int = 30) -> dict:
    """키 없이 쓰는 대역 — 영상 전체에서 '후킹 요소'(숫자·질문·키워드)가 강한
    구간들을 골라 모은다 (연속 구간이 아니라 임팩트 순, 시간순으로 재배열)."""
    n = len(subs)
    if not n:
        return {"keep": [], "reason": "자막이 없습니다"}
    scored = []
    for i, s in enumerate(subs):
        dur = max(0.1, (s.get("end_us", 0) - s.get("start_us", 0)) / 1e6)
        scored.append((_hook_score(str(s.get("text") or ""), dur, i, n), i, dur))
    scored.sort(key=lambda x: (-x[0], x[1]))           # 점수 높은 순
    keep, total = [], 0.0
    for _score, i, dur in scored:
        if total >= target_sec:
            break
        keep.append(i)
        total += dur
    keep.sort()                                        # 영상 순서 유지
    return {"keep": keep,
            "reason": (f"후킹 요소(숫자·질문·키워드)가 강한 {len(keep)}개 구간을 모아 "
                       f"약 {int(total)}초 (대략치 — 제미나이 키를 넣으면 문맥까지 봐요)")}


THUMB_PROMPT = """\
역할: 유튜브 썸네일 카피라이터
대본/주제: "{context}"
위 내용으로 썸네일에 넣을 **짧고 강한 문구** {n}개를 지어줘.
규칙:
- 각 문구는 1~2줄, 한 줄은 아주 짧게(공백 포함 10자 안팎). 두 줄이면 사이에 \\n
- 궁금증·이득·숫자·반전 중 하나로 확 잡기, 과장 낚시는 금지
- 각 문구에서 가장 강조할 단어 1개(highlight)도 골라줘 (문구에 그대로 있는 단어)
출력(JSON만): [{{"title":"1줄\\n2줄","highlight":"강조단어"}}, ...]  (정확히 {n}개)
"""


def suggest_thumbnail_copy(context: str, n: int = 4,
                           model: str = "gemini-2.5-flash", api_key=None) -> list:
    """대본/주제 → 썸네일용 후킹 카피 후보 (title/highlight). 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 썸네일 카피 추천을 쓸 수 없습니다")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": THUMB_PROMPT.format(context=context, n=n)}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"썸네일 카피 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    arr = json.loads(cleaned)
    out = []
    for it in arr if isinstance(arr, list) else []:
        if isinstance(it, dict) and str(it.get("title", "")).strip():
            out.append({"title": str(it["title"]).strip(),
                        "highlight": str(it.get("highlight", "") or "").strip()})
    return out[:n]


def suggest_thumbnail_copy_stub(context: str, n: int = 4) -> list:
    """오프라인 대역 — 키 없이 UI 확인용 템플릿."""
    c = (context.strip() or "이 영상")[:14]
    base = [
        {"title": f"{c}\n이렇게 하세요", "highlight": "이렇게"},
        {"title": f"{c}\n딱 1분 정리", "highlight": "1분"},
        {"title": f"아직도 몰라요?\n{c}", "highlight": "아직도"},
        {"title": f"{c}\n이게 됩니다!", "highlight": "됩니다!"},
    ]
    return base[:n]


def suggest_hooks_stub(context: str, n: int = 5) -> list:
    """오프라인 대역 — 템플릿 기반 후보 (키 없이 UI 확인용)."""
    c = context.strip() or "이 영상"
    templates = [
        f"{c}, 이거 모르면 손해!",
        f"{c} 3가지 핵심 정리",
        f"아직도 {c} 몰라요?",
        f"{c}, 딱 1분이면 끝",
        f"{c} 이렇게 하면 됩니다",
        f"{c}의 반전 결말",
    ]
    return templates[:n]


class StubScript:
    """오프라인 대역 — 데모·테스트용 고정 대본."""

    name = "stub"

    def generate(
        self, topic: str, tone: str = "정보형", target_sec: int = 60, max_chars: int = 22
    ) -> Script:
        return Script(
            title=f"{topic} — 컷대장 데모",
            sentences=[
                f"{topic}, 삼십 초만 집중해 주세요.",
                "이 영상은 컷대장이 자동으로 조립했습니다.",
                "대본과 목소리, 배경과 자막까지 한 번에요.",
                "구독과 좋아요는 큰 힘이 됩니다!",
            ],
            highlights=["집중", "자동", "한 번에요", "구독"],
            background_prompt=f"{topic}를 상징하는 세로형 미니멀 배경, 어두운 톤",
            hashtags=["쇼츠", "자동화", "컷대장"],
        )


SCRIPT_PROVIDERS = {"gemini": GeminiScript, "stub": StubScript}


# ─────────── v0.31: 영상 AI 분석 → 제목·대본 추천 (멀티모달) ───────────

VIDEO_ANALYZE_PROMPT = """\
역할: 유튜브 쇼츠 기획자. 아래는 한 영상의 장면 캡처들{with_tr}이다.
영상 내용을 파악해 JSON으로만 답하라 (설명 없이):
{{
 "summary": "영상 내용 한두 문장 요약",
 "titles": ["유튜브 제목 후보 3개 — 짧고 후킹 있게"],
 "hooks": ["영상 위에 크게 얹을 상단 훅 문구 3개 — 1~2줄, 궁금증/숫자/이득"],
 "script": ["이 영상에 어울리는 내레이션 대본 — 한 문장씩 6~10줄, 각 22자 이내"],
 "hashtags": ["해시태그 5개"]
}}
낚시성 과장 금지. 전부 한국어.
{transcript}"""


def suggest_from_video(frames_b64: list, transcript: str = "",
                       model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """장면 캡처(+자막 텍스트)를 Gemini에 보내 제목·훅·대본·해시태그 추천."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 영상 분석을 쓸 수 없습니다")
    tr = f"\n[영상 속 대사(자동 인식)]\n{transcript.strip()}" if transcript.strip() else ""
    prompt = VIDEO_ANALYZE_PROMPT.format(
        with_tr="과 대사" if tr else "", transcript=tr)
    parts = [{"text": prompt}] + [
        {"inline_data": {"mime_type": "image/jpeg", "data": b64}} for b64 in frames_b64
    ]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseMimeType": "application/json"}}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ScriptError(f"영상 분석 응답 형식 예상 밖: {json.dumps(data)[:250]}") from e
    return {
        "summary": str(out.get("summary", "")),
        "titles": [str(x) for x in out.get("titles", [])][:5],
        "hooks": [str(x) for x in out.get("hooks", [])][:5],
        "script": [str(x) for x in out.get("script", [])][:15],
        "hashtags": [str(x) for x in out.get("hashtags", [])][:8],
    }


def suggest_from_video_stub(frames_b64: list, transcript: str = "") -> dict:
    """오프라인 대역 — 파이프라인 점검용 고정 추천."""
    base = transcript.strip().splitlines()[0][:18] if transcript.strip() else "이 영상"
    return {
        "summary": f"{base} 내용을 담은 영상입니다.",
        "titles": [f"{base}, 이렇게 하면 됩니다", f"{base} 핵심 정리", f"{base} 30초 요약"],
        "hooks": [f"{base} | 핵심", "이거 모르면 손해!", "30초만 보세요"],
        "script": [f"{base}를 소개합니다.", "핵심만 빠르게 짚어드릴게요.",
                   "첫째, 준비물을 확인하세요.", "둘째, 순서대로 따라 하세요.",
                   "마지막으로 결과를 확인합니다.", "구독과 좋아요 부탁드려요!"],
        "hashtags": ["쇼츠", "꿀팁", "자동화", "정리", "요약"],
    }
