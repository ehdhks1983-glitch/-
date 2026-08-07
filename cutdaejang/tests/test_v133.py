"""v1.33 — 목록 62: 블로그 대본 말투·구조 + 「AI로 대본 다듬기」가 안 먹던 것.

회원님 26차:
> "블로그 글로 대본을 만들었을 때 나온 대본이 뭔가 부자연스러운 말투야.
>  글이 이어지는 느낌이 아니고. 그래서 AI로 대본 다듬기를 눌러도 바뀌는 것도 없고.
>  … 후킹하고 설득시킬 수 있는 글의 구조여야 하잖아. AI가 다듬는 것도 제대로 된
>  기능이 되어야 하고"

두 가지 다 **내 프롬프트 문제**였다.

① 대본 프롬프트에 서로 싸우는 두 줄이 있었다:
     «문장당 반드시 22자 이내»  vs  «앞 문장을 받아 자연스럽게 잇고»
   22자는 한국어로 아주 짧은 한 마디다. 길이 제약이 이겨서 «단문 나열»이 된다.
   ⚠ 그 제약은 이제 필요 없다 — 긴 문장은 split_long_subtitles가 두 줄로 나누고
     v1.24부터 문장을 묶어 한 호흡으로 합성한다. 풀 수 있게 된 걸 반영 안 했다.

② 「다듬기」는 버그가 아니라 **엉뚱한 기능**이었다. REFINE_PROMPT은 «받아쓰기 오타
   교정» 전용 — "명백한 오인식만", "못 고치겠는 줄은 원문 그대로 둬". 블로그 대본은
   오인식이 없으니 모델이 **규칙대로** 원문을 그대로 돌려준다.
   버튼이 아무 일도 안 하는 게 «정상 동작»이었다.
"""

import json
import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()


def test_version():
    assert __version__ == "1.51.0"


# ── ① 대본 말투·구조 ───────────────────────────────────────────
def test_the_length_shackle_that_caused_the_staccato_is_gone():
    """🔴 «22자 이내»와 «이어지게»는 같이 못 지킨다 — 길이가 이긴다."""
    p = sg.ARTICLE_SCRIPT_PROMPT
    assert "22자 이내" not in p
    assert "32자 안팎" in p
    # 왜 풀 수 있는지도 프롬프트가 알고 있어야 한다 (모델이 길이를 겁내지 않게)
    assert "자막 두 줄로 알아서 나눈다" in p
    assert "자연스러운 말이 먼저다" in p


def test_the_prompt_now_asks_for_a_persuasive_shape_not_a_list_of_facts():
    """옛 프롬프트는 첫 문장과 마지막만 말하고 **중간이 비어 있었다.**"""
    p = sg.ARTICLE_SCRIPT_PROMPT
    for step in ("훅", "공감·문제", "근거", "핵심·반전", "정리"):
        assert step in p, f"«{step}» 단계 지시가 없다"
    assert "이어서 말하는 한 편의 이야기" in p
    # 리듬 — 다 짧으면 뚝뚝 끊기고 다 길면 늘어진다
    assert "짧은 문장과 조금 긴 문장을" in p
    # 접속사 도배 방지 (기계처럼 들린다)
    assert "연달아 3개를 넘지" in p


def test_facts_still_win_over_structure():
    """🔴 구조를 채우려고 없는 사실을 지어내면 쿠팡 파트너스에서 사고 난다."""
    p = sg.ARTICLE_SCRIPT_PROMPT
    assert "글에 있는 사실만" in p
    assert "지어내지 말 것" in p
    assert "그 단계를 짧게 넘겨라" in p, "구조와 사실이 부딪힐 때 뭘 버릴지 정해 줘야 한다"


# ── ② 다듬기가 «받아쓰기 교정» 전용이던 것 ──────────────────────
def _prompt_used(mode, monkeypatch):
    seen = {}

    def fake(url, payload, headers, **kw):
        seen["p"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [
            {"text": json.dumps({"lines": ["가", "나", "다"]})}]}}]}

    monkeypatch.setattr(sg, "_http_post_json", fake)
    sg.refine_subtitles(["확인 필수", "설치 완료", "그리고 이거 좋아요"],
                        mode=mode, api_key="k" * 20)
    return seen["p"]


def test_a_script_gets_polished_not_spellchecked(monkeypatch):
    """🔴 회원님이 «눌러도 바뀌는 게 없다»고 하신 정체."""
    p = _prompt_used("polish", monkeypatch)
    assert "음성 인식(STT)으로 받아쓴" not in p, "대본에 받아쓰기 교정을 걸면 할 일이 없다"
    assert "«말맛»만" in p
    assert "이어지게" in p and "훅" in p


def test_dictation_still_gets_the_spellcheck(monkeypatch):
    """받아쓴 자막에서는 원래 기능이 그대로여야 한다 (고쳐 놓고 망치면 안 된다)."""
    p = _prompt_used("stt", monkeypatch)
    assert "음성 인식(STT)으로 받아쓴" in p
    assert "명백한 오인식만" in p


def test_stt_is_the_default_so_old_callers_do_not_change_behaviour(monkeypatch):
    """프로그램 안에서 자동으로 부르는 곳(받아쓴 자막)은 손대면 안 된다."""
    p = _prompt_used("stt", monkeypatch)
    seen = {}

    def fake(url, payload, headers, **kw):
        seen["p"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [
            {"text": json.dumps({"lines": ["가"]})}]}}]}

    monkeypatch.setattr(sg, "_http_post_json", fake)
    sg.refine_subtitles(["가"], api_key="k" * 20)      # mode를 안 주면
    assert "음성 인식(STT)으로 받아쓴" in seen["p"]


def test_polish_never_invents_facts_or_changes_line_count():
    p = sg.POLISH_PROMPT
    assert "지어내지 마" in p
    assert "입력 {n}줄 → 출력 정확히 {n}줄" in p
    assert "두 줄로 쪼개지 마" in p
    assert "이미 자연스러운 줄은 그대로" in p     # 억지로 바꾸게 하면 더 나빠진다


def test_line_count_is_still_protected(monkeypatch):
    """모델이 줄 수를 어겨도 화면이 깨지면 안 된다."""
    monkeypatch.setattr(sg, "_http_post_json",
                        lambda url, payload, headers, **kw: {
                            "candidates": [{"content": {"parts": [
                                {"text": json.dumps({"lines": ["하나만"]})}]}}]})
    out = sg.refine_subtitles(["가", "나", "다"], mode="polish", api_key="k" * 20)
    assert out == ["하나만", "나", "다"], "모자란 줄은 원문을 지켜야 한다"


# ── 화면 배선 ─────────────────────────────────────────────────
def test_the_screen_picks_the_right_kind_by_itself():
    """회원님이 «어느 쪽인지» 고르게 하면 안 된다 — 프로그램이 이미 안다."""
    assert "function subsAreScript(" in HTML
    body = HTML.split("function subsAreScript(")[1].split("\nfunction ")[0]
    assert "ep.narration" in body and "ep.script_tts" in body
    assert "if(!ep) return true;" in body        # AI 영상 만들기 = 대본이 원본
    refine = HTML.split("async function refineSubs(")[1].split("\nfunction ")[0]
    assert "subsAreScript() ? 'polish' : 'stt'" in refine


def test_the_server_honours_the_kind():
    body = SRC.split('elif path == "/api/refine_subtitles":')[1].split("\n        elif ")[0]
    assert 'mode = "polish" if params.get("mode") == "polish" else "stt"' in body
    assert "mode=mode" in body


def test_it_says_what_actually_happened():
    """«바뀐 게 없다»는 것도 결과다 — 잠자코 있으면 고장인 줄 안다."""
    refine = HTML.split("async function refineSubs(")[1].split("\nfunction ")[0]
    assert "changed" in refine
    assert "이미 자연스러워서 고칠 곳이 없었어요" in refine
    assert "뜻은 그대로예요" in refine


def test_the_button_no_longer_promises_only_spellcheck():
    """버튼 설명이 «발음 오인식 교정»이라 대본에는 거짓말이었다."""
    btn = HTML.split("refineSubs(event)")[1][:400]
    assert "발음 오인식을 문맥에 맞게 자연스럽게 자동 교정" not in btn
    assert "이어지게" in btn


def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
