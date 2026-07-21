"""v0.64 — 제품 프로필 컨텍스트 주입·정리·오디오 추출."""
import json


def test_gemini_prompt_gets_context_and_guard(monkeypatch):
    from cutdaejang.core import script_generator as sg

    captured = {}
    def fake_post(url, payload, headers):
        captured["text"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "title": "티", "sentences": [{"text": "문장", "highlight": "", "scene": ""}],
            "background_prompt": "", "hashtags": []})}]}}]}
    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    g = sg.GeminiScript.__new__(sg.GeminiScript)
    g.model, g.api_key = "gemini-2.5-flash", "k"

    g.generate("곰대리 소개", context="제품명: 곰대리\n핵심: 클릭 3번 움짤")
    assert "제품명: 곰대리" in captured["text"]
    assert "지어내지 말 것" in captured["text"]          # 할루시네이션 가드
    assert "말하듯 자연스럽게" in captured["text"]

    g.generate("일반 주제")  # 컨텍스트 없으면 블록도 없음
    assert "지어내지 말 것" not in captured["text"]


def test_product_context_builder():
    from cutdaejang.gui.webui import _product_context

    settings = {"products": [{"name": "곰대리", "desc": "움짤 제작기",
                              "points": "클릭 3번\n용량 최적화", "target": "블로거",
                              "tone": "친근", "link": "https://x.y", "avoid": "무료 표현 금지"}]}
    ctx = _product_context({"product": "곰대리", "context_memo": "이번엔 신기능 위주"}, settings)
    for frag in ("제품명: 곰대리", "클릭 3번", "무료 표현 금지", "[이번 영상 참고]", "신기능"):
        assert frag in ctx, frag
    assert _product_context({"product": "없는제품"}, settings) == ""
    assert "메모만" in _product_context({"context_memo": "메모만"}, settings)
