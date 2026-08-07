"""v1.52 — 목록 106·107: 키트 카테고리 가독성 + 상품 후킹 대본·장면 추천.

회원님 52차:
> "업로드 키트 중 유튜브 카테고리도 글씨 잘 보이게" (106)
> "AI로 영상 만드는 건데, 예를 들어 쿠팡파트너스 상품을 끌어왔어.
>  이미지도 들어오고 했으면 상품에 대해서 아는 거잖아.
>  10초짜리 정도에 맞게 대본을 후킹성으로 만들어줘" (107)
"""

import json
import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.53.0"


# ── 106. 유튜브 카테고리 글씨 잘 보이게 ────────────────────────
def test_kit_category_not_dim_hint():
    """카테고리 줄이 hint(흐림)였다 — 네이버클립 카테고리와 같은 규칙으로."""
    assert 'class="hint" id="kitCategory"' not in HTML
    assert '<div id="kitCategory"' in HTML


def test_kit_category_name_highlighted():
    """이름은 노랑·크게, 이유는 옆에 옅게 — 클립 카테고리(v0.87)와 동일 문법."""
    seg = JS.split("kitCategory').innerHTML")[1][:400]
    assert "color:#ffd166;font-size:15px" in seg
    assert "category_reason" in seg


# ── 107. 상품 후킹 대본·장면 추천 ──────────────────────────────
def _fake_post(script="후킹!", scene="줌인 장면"):
    def f(url, payload, key):
        f.prompt = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(
            {"script": script, "scene": scene})}]}}]}
    return f


def test_clip_hook_builds_prompt_scaled_to_seconds(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    fake = _fake_post()
    monkeypatch.setattr(sg, "_post_ai", fake)
    out = sg.clip_hook(product_text="플립8 별점 5.0", seconds=10)
    assert out == {"script": "후킹!", "scene": "줌인 장면"}
    assert "10초" in fake.prompt and "50자" in fake.prompt, "초당 5자 환산"
    assert "플립8 별점 5.0" in fake.prompt


def test_clip_hook_clamps_seconds(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    fake = _fake_post()
    monkeypatch.setattr(sg, "_post_ai", fake)
    sg.clip_hook(product_text="x", seconds=99)
    assert "15초" in fake.prompt, "상한 15초"
    sg.clip_hook(product_text="x", seconds=1)
    assert "4초" in fake.prompt, "하한 4초"


def test_clip_hook_requires_product_info(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(sg.ScriptError, match="상품 정보가 없어요"):
        sg.clip_hook(product_text="", narration="", scene="")


def test_clip_hook_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(sg.ScriptError, match="제미나이 키"):
        sg.clip_hook(product_text="x")


def test_clip_hook_forbids_fake_claims_in_prompt(monkeypatch):
    """과장·허위 금지를 프롬프트에 못 박는다 — 쇼핑 영상은 신뢰가 생명."""
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    fake = _fake_post()
    monkeypatch.setattr(sg, "_post_ai", fake)
    sg.clip_hook(product_text="x")
    assert "있는 사실만" in fake.prompt and "과장 금지" in fake.prompt
    assert "자막은 프로그램이 따로 입힌다" in fake.prompt, "영상에 글자 굽기 방지"


def test_hook_ui_wired_into_clip_dialog():
    for tok in ('id="aiClipHookBtn"', 'id="aiClipHookOut"', 'id="aiClipHookScript"',
                "상품 후킹 대본·장면 추천", "function aiClipHook",
                "function aiClipHookApply", "/api/clip_hook"):
        assert tok in HTML, tok


def test_hook_reads_section_and_product_context():
    """구간 내레이션(.sec-narr)과 끌어온 상품 글(shopPasteText)을 근거로 보낸다."""
    assert "window._aiClipRow" in JS
    assert "shopPasteText" in JS.split("aiClipHook")[1][:1200]


def test_hook_apply_writes_back_to_section():
    """[내레이션에 넣기]는 구간 칸에 쓰고 input 이벤트로 자동 저장을 태운다."""
    body = JS.split("function aiClipHookApply")[1][:800]
    assert ".sec-narr" in body and "dispatchEvent" in body


def test_hook_output_reset_on_open():
    """창을 다시 열면 지난 결과 상자는 접힌다."""
    assert "aiClipHookOut'); if(ho) ho.classList.add('hidden')" in JS
