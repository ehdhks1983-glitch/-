"""v0.71 — 무음(화면분석) 대본 길이 옵션: 요약/원본 분량 + 과압축 버그 수정.

배경: 8분 무음 시연영상을 넣으면 결과가 15초로 과하게 압축되던 문제.
원인 두 가지 — (1) 화면분석 대본이 길이와 무관하게 늘 ~8~14줄, (2) 무음 영상이
목표초 몽타주로 먼저 잘려 원본을 유지할 방법이 없었음. v0.71은 분량을 영상
길이에 비례시키고(요약/원본), 원본 선택 시 몽타주를 건너뛴다.
"""

from cutdaejang.core import script_generator as sg


def _capture(monkeypatch, n_lines_out=3):
    """Gemini 응답을 가로채 프롬프트 텍스트를 확인하게 해주는 헬퍼."""
    seen = {}
    script = ",".join(f'"{i+1}번째 장면"' for i in range(n_lines_out))

    def fake_post(url, payload, headers):
        seen["text"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text":
                '{"summary":"s","titles":["t"],"hooks":["h"],'
                f'"script":[{script}],"hashtags":["a"]}}'}]}}]}

    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    return seen


# ── 1) n_sentences 가 프롬프트 분량 지시로 주입된다 ───────────────────────
def test_n_sentences_injected_into_prompt(monkeypatch):
    seen = _capture(monkeypatch)
    sg.suggest_from_video(["ZmFrZQ=="], topic="블로그 시연", n_sentences=40)
    assert "40줄 내외" in seen["text"]


def test_default_n_sentences_is_10(monkeypatch):
    """인자를 안 주면 예전처럼 10줄 (하위 호환)."""
    seen = _capture(monkeypatch)
    sg.suggest_from_video(["ZmFrZQ=="], topic="x")
    assert "10줄 내외" in seen["text"]


def test_n_sentences_clamped_high_and_low(monkeypatch):
    seen = _capture(monkeypatch)
    sg.suggest_from_video(["ZmFrZQ=="], n_sentences=500)   # 상한 80
    assert "80줄 내외" in seen["text"]
    seen2 = _capture(monkeypatch)
    sg.suggest_from_video(["ZmFrZQ=="], n_sentences=1)     # 하한 4
    assert "4줄 내외" in seen2["text"]


# ── 2) 원본 길이 대본 허용: 결과 캡을 15 → 80 으로 상향 ────────────────────
def test_script_cap_raised_to_80(monkeypatch):
    """원본 8분 walkthrough는 문장이 많다 — 15줄에서 잘리면 과압축된다."""
    seen = _capture(monkeypatch, n_lines_out=90)
    out = sg.suggest_from_video(["ZmFrZQ=="], n_sentences=80)
    assert len(out["script"]) == 80          # 80까지 허용 (예전엔 15에서 잘림)
    assert len(out["script"]) > 15


def test_short_response_not_padded(monkeypatch):
    """짧게 오면 그대로 — 억지로 늘리지 않는다."""
    seen = _capture(monkeypatch, n_lines_out=3)
    out = sg.suggest_from_video(["ZmFrZQ=="], n_sentences=80)
    assert len(out["script"]) == 3


# ── 3) 길이 라우팅 공식 (webui _run_edit 와 동일) ──────────────────────────
def _tgt_auto(narr_analyze, narr_len, narr_target_sec, base=0):
    """webui.py 553~557행의 무음 대본 몽타주 목표 결정 로직 복제."""
    tgt_auto = base
    if narr_analyze:
        tgt_auto = max(20, min(600, int(narr_target_sec))) \
            if narr_len == "summary" else 0
    return tgt_auto


def test_summary_mode_montages_to_target():
    # 요약이면 고른 길이로 몽타주 목표를 잡는다
    assert _tgt_auto(True, "summary", 60) == 60
    assert _tgt_auto(True, "summary", 180) == 180
    assert _tgt_auto(True, "summary", 5) == 20      # 하한 20
    assert _tgt_auto(True, "summary", 9999) == 600  # 상한 600


def test_full_mode_skips_montage():
    # 원본이면 목표 0 → 몽타주 건너뜀 → 전체 길이 유지 (과압축 방지의 핵심)
    assert _tgt_auto(True, "full", 60) == 0


def test_non_analyze_unaffected():
    # 화면분석이 아니면 기존 auto_target 값을 그대로 둔다
    assert _tgt_auto(False, "summary", 60, base=45) == 45


# ── 4) 분량·프레임 수가 길이에 비례 (webui 628~629행 공식) ─────────────────
def _n_sent(dur_s):
    return max(6, min(80, round(dur_s / 4)))


def _nfr(dur_s):
    return max(6, min(20, round(dur_s / 20)))


def test_script_length_scales_with_duration():
    assert _n_sent(16) == 6      # 아주 짧으면 최소 6
    assert _n_sent(60) == 15     # 1분 요약 → 15문장
    assert _n_sent(240) == 60    # 4분 → 60문장
    assert _n_sent(480) == 80    # 8분 원본 → 상한 80 (예전엔 ~14 → 과압축)


def test_frame_count_capped_at_20():
    assert _nfr(30) == 6
    assert _nfr(240) == 12
    assert _nfr(480) == 20       # v0.71: 상한 16 → 20 (긴 원본 대응)


# ── 5) UI: 길이 옵션 요소·전송 필드·라우팅 코드가 실제로 있다 ───────────────
def test_html_has_length_options():
    from cutdaejang.gui import webui
    html = webui._HTML
    assert 'id="narrAnalyzeLenBox"' in html      # 길이 옵션 박스
    assert 'name="narrLen"' in html              # 요약/원본 라디오
    assert 'value="summary"' in html and 'value="full"' in html
    assert 'id="narrLenSec"' in html             # 요약 길이 선택
    assert "onNarrLenChange" in html             # 토글 핸들러
    # 전송 바디에 새 필드가 실린다
    assert "narr_len:" in html
    assert "narr_target_sec:" in html


def test_backend_has_length_routing():
    """소스에 v0.71 라우팅 코드가 존재 — 실수로 지워지면 과압축 재발."""
    import inspect

    from cutdaejang.gui import webui
    src = inspect.getsource(webui._run_edit)
    # 요약이면 목표초로 몽타주, 원본이면 0
    assert 'params.get("narr_len")' in src
    assert 'narr_target_sec' in src
    # 화면분석 대본도 재차 자르지 않도록 배타 조건에 포함
    assert "not narr_analyze" in src
    # 분량을 길이에 비례
    assert "n_sentences=n_sent" in src
