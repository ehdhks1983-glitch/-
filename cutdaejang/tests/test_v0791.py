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
    # v1.02: 섹션 제목이 "[틱톡 — …SEO]"로 확장돼 접두사로 자른다
    tiktok = UPLOAD_KIT_PROMPT.split("[틱톡")[1].split("[인스타그램")[0]
    assert "해요체" in tiktok and "반말 금지" in tiktok


def test_narration_flow_rules_in_script_prompts():
    """대본 프롬프트: 문장이 자연스럽게 이어지는 한 흐름의 내레이션 규칙 (뚝뚝 끊김 방지).

    v1.33(목록 62)에서 블로그 대본 프롬프트를 다시 쓰면서 표현이 «이어 말하는
    내레이션» → «이어서 말하는 한 편의 이야기»로 바뀌었다. 뜻은 더 강해졌으므로
    **문구를 글자 그대로** 보지 않고 «이어짐을 요구하는가»를 본다.
    """
    for p in (PROMPT_TEMPLATE, ARTICLE_SCRIPT_PROMPT):
        assert "이어 말하는 내레이션" in p or "이어서 말하는 한 편의 이야기" in p, p[:80]
        # 앞 문장을 받아 잇게 하는 연결어 지시가 있어야 한다
        assert "그래서" in p and "특히" in p, p[:80]
        assert "나열식" in p or "따로따로 만들어 늘어놓지 말고" in p, p[:80]
    assert "이어지는 한 흐름" in VIDEO_ANALYZE_PROMPT


def test_sentence_ending_rules_in_script_prompts():
    """v0.81: '확인 필수' 같은 명사형(개조식) 종결 금지 — 완결 어미 규칙 (사용자 리포트)."""
    for p in (PROMPT_TEMPLATE, ARTICLE_SCRIPT_PROMPT, VIDEO_ANALYZE_PROMPT):
        assert "명사형" in p and "확인 필수" in p, p[:80]
    # 폴백(원문 문장)도 어미가 잘리지 않게 문장 통째로
    from cutdaejang.core.script_generator import summarize_article_stub

    long_sent = "이 문장은 아주 길어서 예순 자를 넘기지만 어미가 잘리면 안 되는 문장으로 끝까지 완결되게 유지되어야 해요."
    out = summarize_article_stub("제목", long_sent, 45)
    assert out["sentences"][0].endswith("해요.")
