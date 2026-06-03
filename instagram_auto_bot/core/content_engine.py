"""Two-stage text pipeline: plan -> caption, with brand injection + rule enforcement.

Stage 1 produces a plan/copy outline; stage 2 turns it into an Instagram caption
(keyword front-loading, length cap, exact hashtag count).  Generated text is
screened for banned vocabulary; on a hit the caption is regenerated with a
stronger avoidance instruction, up to ``RETRY_COUNT`` times, then blocked.

The engine takes a :class:`~providers.text_base.TextProvider` by injection so it
is fully unit-testable with a fake provider (no SDK / network).
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

import config
from core import content_rules as rules
from core.logging_setup import get_logger
from core.settings_store import SettingsStore
from providers.text_base import ProviderError, TextProvider

log = get_logger("content")


class ContentRuleError(Exception):
    """Raised when generated content cannot be made rule-compliant."""


@dataclass
class PostDraft:
    topic: str
    media_type: str
    title: str
    plan: str
    body: str
    hashtags: List[str]
    warnings: List[str] = field(default_factory=list)

    @property
    def caption(self) -> str:
        return rules.compose_caption(self.body, self.hashtags)


class ContentEngine:
    def __init__(
        self,
        provider: TextProvider,
        store: SettingsStore,
        *,
        rng: Optional[random.Random] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.provider = provider
        self.store = store
        self.rng = rng or random.Random()
        self.max_retries = config.RETRY_COUNT if max_retries is None else max_retries
        self.extra_banned = rules.parse_extra_banned(store.get_str("brand_banned_expressions"))
        self.hashtag_count = self._clamp_count(store.get_int("hashtag_count", config.IG_HASHTAG_COUNT))

    @staticmethod
    def _clamp_count(n: int) -> int:
        n = n or config.IG_HASHTAG_COUNT
        return max(config.IG_HASHTAG_MIN, min(config.IG_HASHTAG_MAX, n))

    # ------------------------------------------------------------ prompts
    def _system_prompt(self) -> str:
        s = self.store
        name = s.get_str("brand_name") or "브랜드"
        tone = s.get_str("brand_tone") or "전문적이고 신뢰감 있는"
        lines = [
            f"너는 '{name}'의 인스타그램 마케팅 콘텐츠를 작성하는 전문 카피라이터다.",
            f"톤앤매너: {tone}.",
        ]
        for label, key in (("타겟 독자", "brand_target"),
                           ("핵심 메시지", "brand_core_message"),
                           ("콘텐츠 컨셉", "brand_concept")):
            val = s.get_str(key)
            if val:
                lines.append(f"{label}: {val}.")
        lines.append(
            "의료 권위(의사·병원·전문의 등)를 주장하거나 연상시키는 표현(가운·청진기 등)을 "
            "절대 쓰지 말 것. 개인 경험담과 객관적 팩트 위주로 작성한다."
        )
        if self.extra_banned:
            lines.append("다음 표현도 절대 쓰지 말 것: " + ", ".join(self.extra_banned) + ".")
        return "\n".join(lines)

    def _plan_prompt(self, topic: str, media_type: str) -> str:
        return (
            f"주제: {topic}\n포맷: {media_type}\n\n"
            "이 주제로 인스타그램 게시물 기획안을 작성하라.\n"
            "1) 한 줄 제목\n2) 핵심 메시지 한 문장\n3) 본문 포인트 3~5개(불릿)\n"
            "과장/허위 없이 팩트와 개인 경험 위주로. 의료 권위 표현 금지."
        )

    def _caption_prompt(self, plan: str, media_type: str) -> str:
        return (
            f"아래 기획안을 바탕으로 인스타그램 {media_type} 캡션을 작성하라.\n\n"
            f"[기획안]\n{plan}\n\n"
            "요구사항:\n"
            f"- 첫 {config.CAPTION_HOOK_LEN}자 안에 핵심 키워드를 배치(프론트로딩).\n"
            f"- 전체 {config.CAPTION_MAX_LEN}자 이내, 자연스러운 줄바꿈 사용.\n"
            f"- 맨 마지막 줄에 해시태그 정확히 {self.hashtag_count}개 "
            "(한국어/영어 혼합 가능, 팔로우·맞팔 같은 스팸성 태그 금지).\n"
            "- 의료 권위(의사·병원·전문의) 표현 금지."
        )

    # ------------------------------------------------------------ provider
    def _safe_generate(self, prompt: str, system: str, *, what: str) -> str:
        last: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                text = self.provider.generate(prompt, system)
                if text and text.strip():
                    return text
                last = ProviderError(f"{what}: 빈 응답")
            except ProviderError as exc:
                last = exc
                log.warning("%s 생성 실패(시도 %d/%d): %s", what, attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    time.sleep(min(config.RETRY_BACKOFF_BASE ** (attempt - 1), 8))
        raise ProviderError(f"{what} 생성 실패: {last}")

    # ------------------------------------------------------------ pipeline
    def generate(self, topic: str, media_type: str = "image") -> PostDraft:
        if not topic or not topic.strip():
            raise ValueError("주제(topic)가 비어 있습니다.")
        system = self._system_prompt()
        plan = self._safe_generate(self._plan_prompt(topic, media_type), system, what="기획")
        plan_banned = rules.find_banned_words(plan, self.extra_banned)
        if plan_banned:
            system = system + "\n[중요] 금지어 감지: " + ", ".join(sorted(set(plan_banned))) + " - 절대 포함 금지."

        last_banned: List[str] = []
        for attempt in range(1, self.max_retries + 1):
            caption_raw = self._safe_generate(
                self._caption_prompt(plan, media_type), system, what="캡션"
            )
            banned = rules.find_banned_words(caption_raw, self.extra_banned)
            if banned:
                last_banned = banned
                log.warning("금지어 감지(캡션 시도 %d/%d): %s", attempt, self.max_retries, banned)
                system = system + "\n[중요] 다음 금지어를 절대 포함하지 말 것: " + ", ".join(sorted(set(banned)))
                continue
            return self._finalize(topic, media_type, plan, caption_raw)

        raise ContentRuleError(
            f"금지어를 제거하지 못해 콘텐츠를 차단했습니다: {sorted(set(last_banned))}"
        )

    def _finalize(self, topic: str, media_type: str, plan: str, caption_raw: str) -> PostDraft:
        body = rules.strip_hashtags(caption_raw)
        raw_tags = rules.extract_hashtags(caption_raw)
        tags = rules.enforce_hashtag_count(
            raw_tags,
            count=self.hashtag_count,
            fill_pool=self._fill_pool(topic),
            extra_banned=self.extra_banned,
            rng=self.rng,
        )
        warnings: List[str] = []
        if len(tags) < self.hashtag_count:
            warnings.append(f"해시태그가 {len(tags)}개로 목표({self.hashtag_count}) 미달")
        report = rules.check_caption(
            rules.compose_caption(body, tags),
            tags,
            expected_count=self.hashtag_count,
            extra_banned=self.extra_banned,
        )
        warnings.extend(n for n in report.notes if "해시태그" not in n)
        title = self._extract_title(plan) or topic.strip()[:60]
        log.info("콘텐츠 생성 완료: '%s' (해시태그 %d개)", title, len(tags))
        return PostDraft(topic, media_type, title, plan, body, tags, warnings)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _extract_title(plan: str) -> str:
        for line in (plan or "").splitlines():
            t = line.strip()
            if not t:
                continue
            # strip list/number markers and a leading "제목:" label
            t = re.sub(r"^\s*(\d+[).\]]|[-*•])\s*", "", t)
            t = re.sub(r"^\s*제목\s*[:：]\s*", "", t)
            return t.strip()
        return ""

    def _fill_pool(self, topic: str) -> List[str]:
        """Candidate hashtags for padding (brand + topic words + safe generics)."""
        pool: List[str] = []
        for src in (self.store.get_str("brand_name"), self.store.get_str("brand_concept"), topic):
            for tok in re.split(r"[\s,./|]+", src or ""):
                tok = tok.strip()
                if len(tok) >= 2:
                    pool.append("#" + tok)
        pool += ["#일상", "#데일리", "#소통", "#기록", "#오늘", "#정보", "#팁", "#리뷰"]
        # de-dupe preserving order
        seen: set[str] = set()
        out: List[str] = []
        for t in pool:
            k = t.lower()
            if k not in seen:
                seen.add(k)
                out.append(t)
        return out
