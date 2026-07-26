"""v0.87 — 업로드 키트 라벨 제거·네이버 클립 카테고리 + 틱톡 감성 + 자막 위치 테마."""

import types

from cutdaejang.gui import webui


def test_v087_ui_present_and_wired():
    html = webui._HTML
    for tok in (
        # 🟢 네이버 클립 — 제목/태그 분리 복사 + 카테고리 추천
        'id="kitNaverTitle"', 'id="kitNaverTags"', 'id="kitNaverCat"',
        "카테고리 추천",
        # 🎵 틱톡 감성 테마 (4개 카드: gen/edit/wl/sec)
        'value="tiktok"', "틱톡 감성", 'id="editThemeSel"',
        # 🎨 자막 위치(가운데) 전달
        "_themePos", "sub_pos",
    ):
        assert tok in html, tok
    # "제목: " 라벨 합성 코드가 사라졌다 (라벨 없이 각 입력란에 그대로)
    assert "'제목: ' + nc.title" not in html
    assert "'토픽 태그: '" not in html
    # 테마 4곳 (gen/edit/wl/sec)
    assert html.count('value="tiktok"') == 5  # gen/edit/wl/sec/shop (v0.89)


def test_upload_kit_prompt_and_stub_have_clip_categories():
    from cutdaejang.core import script_generator as sg

    assert "category1" in sg.UPLOAD_KIT_PROMPT
    assert "category2" in sg.UPLOAD_KIT_PROMPT
    assert "라이프" in sg.UPLOAD_KIT_PROMPT       # 1차 카테고리 후보 목록 포함
    for shorts in (True, False):
        k = sg.suggest_upload_kit_stub("무선 선풍기 후기 영상", "여름 꿀템", is_shorts=shorts)
        nc = k["naver_clip"]
        assert nc["category1"] and nc["category2"]
        assert nc["title"] and len(nc["tags"]) >= 8


def test_sections_style_position_override():
    """params.sub_pos → 구간 대본 렌더 스타일의 자막 위치 (webui 소스 검증 + Style 왕복)."""
    from cutdaejang import config
    from cutdaejang.core.orchestrator import build_style

    style = build_style(config.load_settings())
    assert style.position == "bottom"
    style.position = "center"          # 테마가 덮어쓰는 필드가 실제 존재
    assert style.position == "center"
    src = open(webui.__file__, encoding="utf-8").read()
    # 편집(ep)·구간(params) 두 경로 모두 sub_pos를 style.position으로 반영
    assert src.count('style.position = str(ep["sub_pos"])') == 2   # 렌더 + 분할
    assert 'style.position = str(params["sub_pos"])' in src


def test_dialogue_text_karaoke_used_by_tiktok_theme():
    """틱톡 테마의 karaoke — 단어 시각이 있으면 차오름(\\k), 없으면 안전 폴백."""
    from cutdaejang.core.render_engine.ass_writer import dialogue_text

    style = types.SimpleNamespace(anim="karaoke", primary_color="&HFFFFFF&",
                                  highlight_color="&H00D4FF&", fade=False,
                                  wrap_chars=0)
    with_words = types.SimpleNamespace(
        text="단어 카라오케", highlight="",
        words=[(0, 400_000, "단어"), (400_000, 1_200_000, "카라오케")],
        start_us=0, end_us=1_500_000)
    body = dialogue_text(with_words, style)
    assert "\\k" in body                               # 단어 차오름 태그
    without = types.SimpleNamespace(text="단어 없음 문장", highlight="", words=None,
                                    start_us=0, end_us=1_500_000)
    body2 = dialogue_text(without, style)
    assert "단어 없음 문장" in body2 and "\\k" not in body2   # 폴백해도 자막은 나옴
