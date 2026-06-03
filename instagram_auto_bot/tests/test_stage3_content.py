"""Stage 3 - content rules, two-stage engine, banned-word + hashtag enforcement."""

from __future__ import annotations

import random

import pytest

import config
from core import content_rules as rules
from core.content_engine import ContentEngine, ContentRuleError, PostDraft
from core.settings_store import SettingsStore
from providers.text_base import TextProvider, get_text_provider


# --------------------------------------------------------------------------- #
# Fake provider for deterministic pipeline tests
# --------------------------------------------------------------------------- #
class FakeProvider(TextProvider):
    name = "fake"

    def __init__(self, responses):
        super().__init__(api_key="x", model="fake-model")
        self._responses = list(responses)
        self.calls = []  # (prompt, system)

    def generate(self, prompt: str, system: str = "") -> str:
        self.calls.append((prompt, system))
        if self._responses:
            return self._responses.pop(0)
        return "기본 본문입니다.\n#기본 #태그 #샘플 #콘텐츠 #일상"


CLEAN_CAPTION = (
    "아침 루틴을 공유합니다. 작은 습관이 하루를 바꿔요.\n"
    "오늘부터 같이 시작해요!\n"
    "#아침루틴 #습관 #자기관리 #꾸준함 #일상기록"
)
BANNED_CAPTION = (
    "의사처럼 진단해 드립니다. 병원 가지 마세요.\n"
    "#건강 #루틴 #습관 #자기관리 #일상"
)
PLAN = "1) 아침 루틴의 힘\n2) 작은 습관이 큰 변화를 만든다\n- 기상 후 물 한잔\n- 스트레칭"


# --------------------------------------------------------------------------- #
# content_rules: hashtags
# --------------------------------------------------------------------------- #
def test_normalize_and_extract_hashtags():
    assert rules.normalize_hashtag("  태그 ") == "#태그"
    assert rules.normalize_hashtag("##두번") == "#두번"
    assert rules.normalize_hashtag("#있 음") == "#있음"
    assert rules.extract_hashtags("글 #하나 #둘, 끝") == ["#하나", "#둘"]
    assert rules.strip_hashtags("본문 #하나 #둘") == "본문"


def test_enforce_hashtag_truncates_and_dedupes():
    tags = ["#a", "#b", "#c", "#d", "#e", "#f", "#a"]
    out = rules.enforce_hashtag_count(tags, count=5)
    assert out == ["#a", "#b", "#c", "#d", "#e"]


def test_enforce_hashtag_pads_from_pool():
    out = rules.enforce_hashtag_count(
        ["#one", "#two"], count=5, fill_pool=["#p1", "#p2", "#p3", "#p4"],
        rng=random.Random(0),
    )
    assert len(out) == 5
    assert out[:2] == ["#one", "#two"]
    assert len(set(out)) == 5  # no duplicates


def test_enforce_hashtag_drops_banned_and_spam():
    tags = ["#팔로우", "#좋아요반사", "#의사추천", "#건강루틴"]
    out = rules.enforce_hashtag_count(tags, count=5)
    # spam (#팔로우/#좋아요반사) and banned-word (#의사추천) removed; only clean remains.
    assert out == ["#건강루틴"]


def test_enforce_hashtag_short_when_pool_insufficient():
    out = rules.enforce_hashtag_count(["#only"], count=5, fill_pool=["#one_more"])
    assert out == ["#only", "#one_more"]  # cannot reach 5


# --------------------------------------------------------------------------- #
# content_rules: banned words + caption
# --------------------------------------------------------------------------- #
def test_find_banned_words_default_and_extra():
    assert "의사" in rules.find_banned_words("나는 의사입니다")
    assert "청진기" in rules.find_banned_words("청진기를 들고")        # associative term
    assert rules.find_banned_words("평범한 문장") == []
    assert "경쟁사" in rules.find_banned_words("경쟁사 제품", extra=["경쟁사"])


def test_parse_extra_banned_splits():
    assert rules.parse_extra_banned("a, b\n c ,") == ["a", "b", "c"]


def test_compose_caption_respects_max_len():
    body = "가" * 5000
    tags = ["#하나", "#둘", "#셋"]
    out = rules.compose_caption(body, tags, max_len=config.CAPTION_MAX_LEN)
    assert len(out) <= config.CAPTION_MAX_LEN
    assert out.endswith("#하나 #둘 #셋")


def test_check_caption_flags_problems():
    rep = rules.check_caption("#태그로시작", ["#a", "#b"], expected_count=5)
    assert rep.ok is False
    assert rep.hook_ok is False
    assert rep.hashtag_count == 2


# --------------------------------------------------------------------------- #
# ContentEngine pipeline
# --------------------------------------------------------------------------- #
def _store(tmp_home, **over):
    store = SettingsStore().load()
    store.set("brand_name", over.get("brand_name", "테스트브랜드"))
    store.set("brand_tone", over.get("brand_tone", "유쾌하고 친근한"))
    for k, v in over.items():
        store.set(k, v)
    return store


def test_engine_happy_path(tmp_home):
    provider = FakeProvider([PLAN, CLEAN_CAPTION])
    engine = ContentEngine(provider, _store(tmp_home), rng=random.Random(0), max_retries=3)
    draft = engine.generate("아침 루틴", media_type="image")

    assert isinstance(draft, PostDraft)
    assert len(draft.hashtags) == config.IG_HASHTAG_COUNT  # exactly 5
    assert "#" not in draft.body                            # hashtags stripped from body
    assert draft.title == "아침 루틴의 힘"                    # from plan, markers stripped
    assert rules.find_banned_words(draft.caption) == []     # clean


def test_engine_injects_brand_into_system_prompt(tmp_home):
    provider = FakeProvider([PLAN, CLEAN_CAPTION])
    engine = ContentEngine(provider, _store(tmp_home, brand_name="브랜드X", brand_tone="시크한"),
                           rng=random.Random(0))
    engine.generate("주제")
    system_used = provider.calls[0][1]
    assert "브랜드X" in system_used and "시크한" in system_used
    assert "의료 권위" in system_used                         # always-on guardrail


def test_engine_retries_on_banned_then_succeeds(tmp_home):
    provider = FakeProvider([PLAN, BANNED_CAPTION, CLEAN_CAPTION])
    engine = ContentEngine(provider, _store(tmp_home), rng=random.Random(0), max_retries=3)
    draft = engine.generate("아침 루틴")
    assert rules.find_banned_words(draft.caption) == []
    # plan + 2 caption attempts == 3 provider calls
    assert len(provider.calls) == 3
    # the retry system prompt explicitly forbids the detected word
    assert any("의사" in system for _, system in provider.calls[2:])


def test_engine_blocks_when_banned_persists(tmp_home):
    provider = FakeProvider([PLAN, BANNED_CAPTION, BANNED_CAPTION, BANNED_CAPTION])
    engine = ContentEngine(provider, _store(tmp_home), rng=random.Random(0), max_retries=3)
    with pytest.raises(ContentRuleError):
        engine.generate("아침 루틴")


def test_engine_clamps_hashtag_count(tmp_home):
    provider = FakeProvider([PLAN, CLEAN_CAPTION])
    engine = ContentEngine(provider, _store(tmp_home, hashtag_count=20), rng=random.Random(0))
    assert engine.hashtag_count == config.IG_HASHTAG_MAX     # 20 clamped to 7
    draft = engine.generate("주제")
    assert len(draft.hashtags) <= config.IG_HASHTAG_MAX


def test_engine_pads_when_caption_has_few_tags(tmp_home):
    caption_two_tags = "본문 텍스트입니다.\n#하나 #둘"
    provider = FakeProvider([PLAN, caption_two_tags])
    engine = ContentEngine(provider, _store(tmp_home), rng=random.Random(1))
    draft = engine.generate("아침 루틴 건강 습관")
    assert len(draft.hashtags) == config.IG_HASHTAG_COUNT     # padded from pool to 5


# --------------------------------------------------------------------------- #
# Provider factory
# --------------------------------------------------------------------------- #
def test_factory_returns_expected_types():
    assert get_text_provider("claude").__class__.__name__ == "ClaudeTextProvider"
    assert get_text_provider("openai").__class__.__name__ == "OpenAITextProvider"
    assert get_text_provider("gemini").__class__.__name__ == "GeminiTextProvider"
    with pytest.raises(ValueError):
        get_text_provider("nope")


def test_factory_defaults_model_per_provider():
    p = get_text_provider("claude")
    assert p.model == config.DEFAULT_TEXT_MODELS["claude"]
    p2 = get_text_provider("openai", model="custom-x")
    assert p2.model == "custom-x"
