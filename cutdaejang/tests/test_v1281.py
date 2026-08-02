"""v1.28.1 — 목록 56(업로드 키트가 «모양» 때문에 터지던 것) + 52(실패 이유 갈라 안내).

회원님 23차:
> "왜 업데이트했는데 동일하게 업로드 키트가 안 되는 거야?"

v1.28.0에서 모델 자동 교체(목록 53)를 넣었고, 실제 업로드 키트 경로에
회원님이 받으신 404를 그대로 먹여 보니 **교체 자체는 성공**했다. 그런데 그다음
`normalize_kit`이 `AttributeError: 'str' object has no attribute 'get'`로 터졌다.
모델을 바꾸면 답하는 **모양**이 달라지는데 예전 코드는 한 모양만 받았기 때문이다.
그리고 그 예외는 아무도 안 받아 화면엔 «서버 내부 오류»만 떴다.

또 하나 — 예전엔 429를 통째로 «한도·크레딧 소진»이라고만 안내했다. 회원님이
"충전은 다 되어 있는데"를 몇 번이나 되물으신 이유가 이것이다. ①1분 ②하루 ③크레딧은
해야 할 일이 서로 완전히 다르다.
"""

import json
import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import gemini_models as gm
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)

# 구글이 실제로 돌려주는 응답 — 회원님 로그·구글 문서에서 그대로 가져왔다.
RATE = ('HTTP 429: {"error":{"code":429,"message":"You exceeded your current quota, '
        'please check your plan and billing details.","status":"RESOURCE_EXHAUSTED",'
        '"details":[{"@type":"type.googleapis.com/google.rpc.QuotaFailure","violations":'
        '[{"quotaId":"GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},'
        '{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"27s"}]}}')
DAY = ('HTTP 429: {"error":{"code":429,"message":"You exceeded your current quota.",'
       '"details":[{"violations":[{"quotaId":'
       '"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
CRED = ('HTTP 429: {"error":{"code":429,"message":"Your prepayment credits are depleted. '
        'Please purchase more credits.","status":"RESOURCE_EXHAUSTED"}}')
GONE = ('API 오류 404: {"error":{"code":404,"message":"This model models/gemini-2.5-flash '
        'is no longer available to new users.","status":"NOT_FOUND"}}')
BADKEY = ('HTTP 400: {"error":{"message":"API key not valid. Please pass a valid API key.",'
          '"details":[{"reason":"API_KEY_INVALID"}]}}')


def test_version():
    assert __version__ == "1.32.0"


# ── 목록 52: 실패 이유를 갈라 본다 ─────────────────────────────
@pytest.mark.parametrize("text,kind", [
    (RATE, "quota_minute"),
    (DAY, "quota_day"),
    (CRED, "credits"),
    (GONE, "model_gone"),
    (BADKEY, "key"),
    ("HTTP 429 RESOURCE_EXHAUSTED", "quota"),      # 구글이 자세히 안 알려준 429
    ("ffmpeg 실패: no such file", ""),             # 우리가 아는 유형이 아니다
])
def test_classify_error(text, kind):
    assert gm.classify_error(text) == kind


def test_billing_details_wording_is_not_mistaken_for_empty_credits():
    """🔴 만들면서 실제로 한 번 틀린 자리.

    무료 «분당» 한도 응답의 원문에도 "check your plan and billing details"가 들어 있다.
    'billing'만 보고 «크레딧 0»으로 안내하면, 27초만 쉬면 될 회원님을 결제 화면으로
    보내게 된다 — 정확히 지금 회원님이 겪고 계신 혼란을 한 번 더 만드는 셈이다.
    """
    assert "billing details" in RATE          # 이 문구가 실제로 들어 있음을 못 박는다
    assert gm.classify_error(RATE) == "quota_minute"


def test_quota_id_beats_guessing():
    """구글이 «어느 한도»인지 이름을 주면 글로 짐작하지 않는다."""
    mixed = DAY.replace("You exceeded your current quota.",
                        "Requests per minute exceeded, check billing details")
    assert gm.classify_error(mixed) == "quota_day"


def test_retry_delay_and_google_message_are_extracted():
    assert gm.retry_delay_s(RATE) == 27.0
    assert gm.retry_delay_s(DAY) is None
    assert "billing details" in gm.google_message(RATE)
    assert gm.google_message("어디에도 message가 없음") == ""


def test_error_text_says_what_to_do_and_shows_the_original():
    """안내는 «무슨 일인지»만이 아니라 «지금 뭘 하면 되는지»까지 있어야 한다."""
    minute = gm.error_text(RATE)
    assert "분" in minute and "기다" in minute or "잠시" in minute
    assert "GenerateRequestsPerMinutePerProjectPerModel-FreeTier" in minute  # 원문 근거

    day = gm.error_text(DAY)
    assert "오늘" in day and "4~5시" in day

    cred = gm.error_text(CRED)
    assert "크레딧" in cred and "프로젝트" in cred
    # 셋은 서로 다른 글이어야 한다 (예전엔 셋 다 같은 문장이었다)
    assert len({minute, day, cred}) == 3
    assert gm.error_text("ffmpeg 실패") == ""      # 모르는 건 손대지 않는다


def test_minute_limit_waits_and_retries_but_credits_do_not(monkeypatch):
    """분당 한도는 «구글이 알려준 만큼» 쉬었다 다시 — 크레딧 0은 즉시 포기.

    크레딧 0에서 기다리면 회원님은 아무 이유 없이 몇 분을 멍하니 보게 된다.
    """
    naps: list = []
    monkeypatch.setattr(gm, "_sleep", naps.append)
    monkeypatch.setattr(gm, "list_available", lambda k, timeout=20.0: ["gemini-flash-latest"])

    for text, want_calls, want_naps in ((RATE, 3, [27.0, 27.0]), (CRED, 1, [])):
        naps.clear()
        calls: list = []

        def poster(url, payload, headers, **kw):
            calls.append(url)
            raise RuntimeError(text)

        with pytest.raises(RuntimeError):
            gm.post_generate("gemini-flash-latest", {}, "k" * 20, poster=poster)
        assert len(calls) == want_calls, f"{text[:30]}: 호출 {len(calls)}회"
        assert naps == want_naps


def test_model_switch_still_works_after_the_retry_rewrite():
    """목록 53의 자동 교체가 재시도 코드를 넣으면서 깨지지 않았는지."""
    gm.list_available = lambda k, timeout=20.0: ["gemini-flash-latest", "gemini-2.0-flash"]
    names: list = []

    def poster(url, payload, headers, **kw):
        n = url.split("/models/")[1].split(":")[0]
        names.append(n)
        if n == "죽은모델":
            raise RuntimeError(GONE)
        return {"ok": True}

    assert gm.post_generate("죽은모델", {}, "k" * 20, poster=poster) == {"ok": True}
    assert names == ["죽은모델", "gemini-flash-latest"]


# ── 목록 56: 응답 «모양»이 달라도 안 터진다 ─────────────────────
def _kit_from(obj, monkeypatch):
    monkeypatch.setattr(
        sg, "_http_post_json",
        lambda url, payload, headers, **kw: {
            "candidates": [{"content": {"parts": [
                {"text": json.dumps(obj, ensure_ascii=False)}]}}]})
    return sg.suggest_upload_kit([], "대사", api_key="k" * 20)


def test_kit_survives_a_string_where_an_object_was_expected(monkeypatch):
    """🔴 회원님 화면을 죽이던 바로 그 예외.

    실제 업로드 키트 경로에 회원님 404를 먹였더니 모델 교체는 성공했는데
    그다음 `'str' object has no attribute 'get'`로 터졌다.
    """
    kit = _kit_from({"titles": ["제목1"], "tiktok": "캡션만 문자열로",
                     "threads": "스레드 글", "naver_clip": "네이버 제목",
                     "instagram": "인스타 캡션"}, monkeypatch)
    assert kit["tiktok"]["caption"] == "캡션만 문자열로"
    assert kit["threads"]["post"] == "스레드 글"
    assert kit["naver_clip"]["title"] == "네이버 제목"
    assert kit["instagram"]["caption"] == "인스타 캡션"


def test_kit_does_not_shred_a_string_into_letters(monkeypatch):
    """🔴 더 나쁜 쪽 — 터지지 않고 **조용히 망가지던** 것.

    `"tags": "태그,둘,셋"`이 오면 예전엔 `['태','그',',','둘',…]`가 되어
    화면에 글자가 낱개로 뿌려졌다. 회원님은 «AI가 이상하다»고만 보이셨을 것이다.
    """
    kit = _kit_from({"titles": "제목 하나, 쉼표가 있음", "tags": "태그,둘,셋",
                     "hashtags": "#꿀팁,#정리"}, monkeypatch)
    assert kit["tags"] == ["태그", "둘", "셋"]
    assert kit["hashtags"] == ["꿀팁", "정리"]
    # 제목은 쉼표를 품는 게 정상이라 쉼표로 자르면 안 된다
    assert kit["titles"] == ["제목 하나, 쉼표가 있음"]


def test_kit_splits_a_multiline_string_by_lines(monkeypatch):
    kit = _kit_from({"titles": "제목1\n제목2\n제목3"}, monkeypatch)
    assert kit["titles"] == ["제목1", "제목2", "제목3"]


def test_kit_handles_a_completely_wrong_response(monkeypatch):
    """목록(list)으로 답하는 모델이 있어도 화면은 살아 있어야 한다."""
    kit = _kit_from(["a", "b"], monkeypatch)
    assert kit["titles"] == [] and kit["category"] == "인물/블로그"
    assert kit["tiktok"]["caption"] == ""


def test_normal_shape_is_unchanged(monkeypatch):
    """모양을 넓게 받되 원래 잘 되던 응답의 결과는 그대로여야 한다."""
    kit = _kit_from({"titles": ["ㄱ", "ㄴ"], "tags": ["t1", "t2"],
                     "hashtags": ["#a", "b"], "category": "과학기술",
                     "tiktok": {"caption": "c", "hashtags": ["x"], "title": "tt"}},
                    monkeypatch)
    assert kit["titles"] == ["ㄱ", "ㄴ"] and kit["tags"] == ["t1", "t2"]
    assert kit["hashtags"] == ["a", "b"] and kit["category"] == "과학기술"
    assert kit["tiktok"] == {"caption": "c", "hashtags": ["x"], "title": "tt"}


# ── 화면·서버 배선 ─────────────────────────────────────────────
def test_upload_kit_falls_back_instead_of_500():
    """AI가 **어떤 식으로** 실패하든 예시 키트는 나와야 한다.

    예전엔 `except sg.ScriptError`만 있어 모양 문제(AttributeError·TypeError)는
    그대로 500으로 튀었다 — 화면엔 «서버 내부 오류»만 남았다.
    """
    src = (webui.__file__ and open(webui.__file__, encoding="utf-8").read())
    body = src.split("def _upload_kit(")[1].split("\n    def ")[0]
    assert "except Exception as e:" in body, "ScriptError만 받으면 모양 문제에 또 터진다"
    assert "stub_reason" in body
    assert body.count("suggest_upload_kit_stub") == 2       # 키 없음 + 실패 둘 다


def test_kit_screen_shows_the_real_reason_not_a_key_excuse():
    """키가 멀쩡한데 «키가 없어 예시»라고 뜨면 회원님은 키만 계속 다시 넣게 된다."""
    assert "data.stub_reason" in HTML
    assert "아래는 예시 문구예요" in HTML


def test_server_guard_uses_the_new_explainer():
    src = open(webui.__file__, encoding="utf-8").read()
    guard = src.split("def do_POST(")[1].split("\n    def ")[0]
    assert "_gm.error_text(str(e))" in guard
    # 세 상황을 한 문장으로 뭉뚱그리던 옛 안내는 사라져야 한다
    assert "Gemini 한도·크레딧이 소진돼 요청이 실패했어요" not in src


def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML


# ── 목록 56-b: 같은 결함이 AI 기능 다섯 곳에 더 있었다 ──────────
def _reply(monkeypatch, obj):
    monkeypatch.setattr(
        sg, "_http_post_json",
        lambda url, payload, headers, **kw: {"candidates": [{"content": {"parts": [
            {"text": json.dumps(obj, ensure_ascii=False)}]}}]})


SUBS = [{"text": f"문장{i}", "start_us": i * 1_000_000, "end_us": (i + 1) * 1_000_000}
        for i in range(10)]
K = "k" * 20

# 업로드 키트만 고치면 회원님은 «다음 기능»에서 똑같이 막힌다 — 전부 확인한다.
AI_CALLS = [
    ("구간 나누기", lambda: sg.split_script_sections_ai("본문 " * 80, api_key=K)),
    ("제품 정리", lambda: sg.summarize_product("설명 " * 30, api_key=K)),
    ("블로그→대본", lambda: sg.summarize_article("제목", "본문 " * 80, api_key=K)),
    ("핵심 선별", lambda: sg.suggest_highlights(SUBS, 20, api_key=K)),
    ("대본 다듬기", lambda: sg.refine_subtitles([s["text"] for s in SUBS], api_key=K)),
    ("영상 분석", lambda: sg.suggest_from_video([], "대사", api_key=K)),
    ("훅 추천", lambda: sg.suggest_hooks("맥락", api_key=K)),
    ("썸네일 문구", lambda: sg.suggest_thumbnail_copy("맥락", api_key=K)),
]


@pytest.mark.parametrize("name,call", AI_CALLS, ids=[n for n, _ in AI_CALLS])
@pytest.mark.parametrize("shape", [["a", "b"], "그냥 글", 7], ids=["목록", "문자열", "숫자"])
def test_every_ai_call_survives_a_wrong_shaped_reply(monkeypatch, name, call, shape):
    """🔴 직전 커밋본에서 여섯 곳 중 다섯이 AttributeError로 터졌다 (실측).

    터지면 화면엔 «서버 내부 오류»만 남아 회원님은 뭘 해야 할지 알 수 없다.
    한국어 안내(ScriptError)로 나오든 빈 결과로 나오든, **터지지만 않으면** 된다.
    """
    _reply(monkeypatch, shape)
    try:
        call()
    except sg.ScriptError:
        pass                                   # 이유를 말해 주는 실패는 정상
    except Exception as e:                     # noqa: BLE001
        pytest.fail(f"{name}: {type(e).__name__} — 화면엔 «서버 내부 오류»만 뜬다: {e}")


def test_highlight_indices_accept_numbers_in_any_shape(monkeypatch):
    """번호를 3 / "3" / 3.0 어느 모양으로 줘도 받는다 — 예전엔 3.0에서 ValueError."""
    _reply(monkeypatch, {"keep": [0, "2", 4.0, "글자", None, 999]})
    assert sg.suggest_highlights(SUBS, 20, api_key=K)["keep"] == [0, 2, 4]


def test_script_json_that_is_not_an_object_is_a_clean_error():
    with pytest.raises(sg.ScriptParseError):
        sg.Script.from_json_text('["문장1", "문장2"]')
