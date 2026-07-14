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
