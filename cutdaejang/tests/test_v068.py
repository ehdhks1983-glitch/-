"""v0.68 — 이미지 프롬프트 서술 구조 + 영상 길이 직접 입력 클램프."""

from cutdaejang.core import background_generator as bg


def test_scene_prompt_narrative_structure():
    """서술형: 매체 → 장면 → 구도·조명·품질 꼬리 → 글자 금지 (순서·요소)."""
    t = bg.scene_prompt_text("카페에서 노트북을 켠다", "실사풍", "")
    # 매체(스타일)가 맨 앞
    assert t.startswith(bg.IMAGE_STYLES["실사풍"])
    # 장면이 들어간다
    assert "카페에서 노트북을 켠다" in t
    # 구도·조명·품질 꼬리
    assert "구도" in t and ("초점" in t or "디테일" in t)
    # 글자 금지 가드는 항상 마지막
    assert t.rstrip().endswith(")") and "글자" in t and "절대 넣지 말 것" in t


def test_image_styles_are_descriptive():
    """v0.68: 프리셋이 단어 하나가 아니라 색감·조명 등을 담은 서술이어야."""
    for key, desc in bg.IMAGE_STYLES.items():
        assert len(desc) >= 20, key            # 충분히 서술적
        assert "," in desc, key                # 여러 요소 나열


def test_scene_prompt_character_and_scene_together():
    """캐릭터 + 장면이 함께 있으면 한 문장으로 자연스럽게 엮인다."""
    t = bg.scene_prompt_text("책을 읽는다", "3D", "곰대리")
    assert "곰대리" in t and "책을 읽는다" in t and "같은 그림체" in t


def test_no_text_guard_always_present():
    """장면이 비어도 글자 금지 가드는 유지된다."""
    t = bg.scene_prompt_text("", "미니멀", "")
    assert "절대 넣지 말 것" in t
