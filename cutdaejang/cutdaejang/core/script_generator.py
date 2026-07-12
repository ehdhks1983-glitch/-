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
- 문장당 {max_chars}자 이내 (자막 1줄)
- 구어체. 숫자·영어 약어는 한글 발음으로 표기 (TTS 오독 방지. 예: "2026년"→"이천이십육년", "AI"→"에이아이")
출력(JSON만): {{"title":"","sentences":["",...],"background_prompt":"","hashtags":[""]}}
"""


@dataclass
class Script:
    title: str
    sentences: List[str]
    background_prompt: str = ""
    hashtags: List[str] = field(default_factory=list)

    @classmethod
    def from_json_text(cls, text: str) -> "Script":
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ScriptParseError(f"대본 JSON 파싱 실패: {e}\n원문 앞부분: {cleaned[:200]}") from e
        sentences = data.get("sentences")
        if (
            not isinstance(sentences, list)
            or not sentences
            or not all(isinstance(s, str) and s.strip() for s in sentences)
        ):
            raise ScriptParseError(f"sentences 형식 오류: {sentences!r}")
        return cls(
            title=str(data.get("title", "")),
            sentences=[s.strip() for s in sentences],
            background_prompt=str(data.get("background_prompt", "")),
            hashtags=[str(h) for h in data.get("hashtags", []) if h],
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "sentences": self.sentences,
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
            background_prompt=f"{topic}를 상징하는 세로형 미니멀 배경, 어두운 톤",
            hashtags=["쇼츠", "자동화", "컷대장"],
        )


SCRIPT_PROVIDERS = {"gemini": GeminiScript, "stub": StubScript}
