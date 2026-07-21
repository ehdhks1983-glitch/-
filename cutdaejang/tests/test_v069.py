"""v0.69 — 무음 영상 화면 분석: 주제 힌트 프롬프트 주입 + 프레임 수 스케일."""

from cutdaejang.core import script_generator as sg


def _capture(monkeypatch):
    seen = {}

    def fake_post(url, payload, headers):
        seen["payload"] = payload
        seen["text"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text":
                '{"summary":"s","titles":["t"],"hooks":["h"],'
                '"script":["첫 장면 소개","둘째 단계 진행","마무리"],"hashtags":["a"]}'}]}}]}

    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    return seen


def test_topic_hint_injected_into_prompt(monkeypatch):
    seen = _capture(monkeypatch)
    out = sg.suggest_from_video(["ZmFrZQ=="], transcript="", topic="블로그 글쓰기 시연")
    assert "블로그 글쓰기 시연" in seen["text"]
    assert "이 주제에 맞춰" in seen["text"]
    # 무음(대사 없음)이어도 대본이 나온다
    assert out["script"] == ["첫 장면 소개", "둘째 단계 진행", "마무리"]
    # 프레임이 inline_data로 실려간다
    parts = seen["payload"]["contents"][0]["parts"]
    assert any("inline_data" in p for p in parts)


def test_no_topic_no_hint(monkeypatch):
    seen = _capture(monkeypatch)
    sg.suggest_from_video(["ZmFrZQ=="], transcript="", topic="")
    assert "이 주제에 맞춰" not in seen["text"]
    # 무음이면 대사 블록도 없다
    assert "영상 속 대사" not in seen["text"]


def test_frame_count_scales_with_duration():
    """webui 화면분석의 프레임 수 공식: 길이 비례 6~20컷 (4분 → 12컷).

    (v0.71에서 긴 원본 대응으로 상한을 16 → 20으로 상향.)
    """
    def nfr(dur_s):
        return max(6, min(20, round(dur_s / 20)))

    assert nfr(30) == 6          # 짧으면 최소 6
    assert nfr(240) == 12        # 4분 → 12컷
    assert nfr(600) == 20        # 길어도 최대 20
