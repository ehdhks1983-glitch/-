"""v0.79.1 — 플랫폼별 말투 규칙(스레드·틱톡) + 내레이션 이어짐 규칙 (프롬프트 회귀 방지)."""

from cutdaejang.core.script_generator import (
    ARTICLE_SCRIPT_PROMPT,
    PROMPT_TEMPLATE,
    UPLOAD_KIT_PROMPT,
    VIDEO_ANALYZE_PROMPT,
)


def test_threads_tone_friendly_banmal_not_rude():
    """스레드: 다정한 반말 — '야'·'~했냐' 같은 거친 말투는 금지로 명시."""
    assert "부드러운 반말" in UPLOAD_KIT_PROMPT
    assert "했냐" in UPLOAD_KIT_PROMPT           # 금지 예시로 명시돼 있어야 함
    assert "부름말" in UPLOAD_KIT_PROMPT         # "야"류 시작 금지
    assert "시비조" in UPLOAD_KIT_PROMPT
    assert "다정하게" in UPLOAD_KIT_PROMPT


def test_tiktok_tone_polite():
    """틱톡: 해요체(존댓말) — 반말 금지 명시 (사용자 리포트: 틱톡은 반말 형식 아님)."""
    tiktok = UPLOAD_KIT_PROMPT.split("[틱톡]")[1].split("[인스타그램")[0]
    assert "해요체" in tiktok and "반말 금지" in tiktok


def test_narration_flow_rules_in_script_prompts():
    """대본 프롬프트: 문장이 자연스럽게 이어지는 한 흐름의 내레이션 규칙 (뚝뚝 끊김 방지)."""
    for p in (PROMPT_TEMPLATE, ARTICLE_SCRIPT_PROMPT):
        assert "이어 말하는 내레이션" in p, p[:80]
        assert "나열식" in p
    assert "이어지는 한 흐름" in VIDEO_ANALYZE_PROMPT
