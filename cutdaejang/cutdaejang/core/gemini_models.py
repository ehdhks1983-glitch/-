"""제미나이 글 모델 자동 선택 (v1.27.1, 목록 53).

회원님 22차 리포트:
    404: "This model models/gemini-2.5-flash is no longer available to new users.
          Please update your code to use a newer model."

**구글이 모델을 퇴역시키면 그 이름을 박아 둔 프로그램은 통째로 멈춘다.**
지금까지 `gemini-2.5-flash`가 11곳에 하드코딩돼 있어서, 새로 키를 발급한
회원(= 앞으로 사실 모든 새 구매자)은 대본·업로드 키트·요약·자막 다듬기·음성 인식이
**전부** 안 됐다. 크레딧이 있든 없든 상관없이.

그래서 이름을 박지 않고 **계정이 실제로 쓸 수 있는 모델을 API에 물어본다.**
  ① 키로 `GET /v1beta/models`를 불러 쓸 수 있는 목록을 받는다 (한 번만, 캐시)
  ② 설정에 적힌 모델이 그 목록에 있으면 그대로 쓴다
  ③ 없으면 선호 순서대로 고르고, 그것도 없으면 **목록에서 직접 고른다**
     (generateContent 지원 + 이미지/음성 전용 제외 + flash 우선 + 최신 버전 우선)
  ④ 그래도 404가 나면 그 이름을 '없어진 것'으로 표시하고 다시 고른다

③이 핵심이다 — 구글이 «gemini-4-flash» 같은 걸 내놔도 프로그램을 다시 안 만들어도 된다.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

log = logging.getLogger("cutdaejang")

_BASE = "https://generativelanguage.googleapis.com/v1beta"

# 아는 이름은 새것부터 — 단, **API가 있다고 한 것만** 쓴다 (없는 이름은 건너뜀)
TEXT_PREFERENCE = (
    "gemini-flash-latest",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
)

# 글 생성에 쓰면 안 되는 것들 (음성·이미지·임베딩 전용)
_NOT_TEXT = ("tts", "image", "embedding", "embed", "aqa", "veo", "imagen", "learnlm")

_MODEL_GONE_MARKS = ("no longer available", "not found", "NOT_FOUND", "404",
                     "is not supported", "does not exist")

# 🩺 v1.28.1 (목록 52): 실패 이유를 한 낱말로 가른다.
#   회원님이 «충전은 다 되어 있는데 왜 안 되냐»고 몇 번을 물으셨다. 그때 화면에 뜨던
#   글은 세 가지 전혀 다른 상황을 **한 문장으로 뭉뚱그린** 것이었다:
#     ① 분당 한도 — 몇 십 초만 쉬면 풀린다 (프로그램이 알아서 기다리면 된다)
#     ② 하루 무료 한도 — 내일 풀린다. 오늘은 아무리 눌러도 안 된다
#     ③ 선불 크레딧 0 — 기다려도 절대 안 풀린다. 결제·프로젝트를 봐야 한다
#   ①과 ③을 같은 글로 안내하면 회원님은 하루를 통째로 헛기다린다.
_KEY_MARKS = ("api_key_invalid", "api key not valid", "permission_denied",
              "invalid authentication", "api key expired")
#   ⚠ "billing"만 걸러선 안 된다 — 무료 «분당» 한도 원문에도
#     "check your plan and billing details"가 들어 있어 정반대로 안내하게 된다.
_CREDIT_MARKS = ("prepayment credit", "credits are depleted", "billing account",
                 "billingnotactive", "billing_not_active", "quota of 0",
                 "purchase more credits")

_sleep = time.sleep          # 시험에서 갈아 끼운다 (실제로 안 기다리게)

_lock = threading.Lock()
_avail_cache: dict = {}       # api_key 뒷자리 → [모델 이름]
_gone: set = set()            # 404를 받은 이름
_resolved: dict = {}          # (want, key꼬리) → 실제로 쓸 이름


def is_model_gone(text: str) -> bool:
    """이 오류가 '모델이 없어졌다'인가 (크레딧·한도 문제와 구분)."""
    t = str(text or "")
    return any(m.lower() in t.lower() for m in _MODEL_GONE_MARKS)


def _quota_ids(text: str) -> List[str]:
    """구글이 알려준 «어느 한도에 걸렸는지» 이름 — 이게 있으면 추측할 필요가 없다."""
    return re.findall(r'"quotaId"\s*:\s*"([^"]+)"', str(text or ""))


def retry_delay_s(text: str) -> Optional[float]:
    """429 응답이 «몇 초 뒤에 다시 오라»고 알려준 값 (RetryInfo)."""
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', str(text or ""))
    if m:
        return float(m.group(1))
    m = re.search(r"retry in ([\d.]+)\s*s", str(text or ""), re.IGNORECASE)
    return float(m.group(1)) if m else None


def google_message(text: str) -> str:
    """응답 안의 구글 원문 한 줄 — 회원님이 그대로 복사해 보내실 수 있게."""
    m = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', str(text or ""))
    if not m:
        return ""
    try:
        return json.loads(f'"{m.group(1)}"')[:300]
    except (ValueError, json.JSONDecodeError):
        return m.group(1)[:300]


def classify_error(text: str) -> str:
    """실패 이유를 한 낱말로 (v1.28.1, 목록 52).

    돌려주는 값: model_gone / key / credits / quota_day / quota_minute / quota / ""
    """
    t = str(text or "")
    low = t.lower()
    is_429 = "429" in t or "resource_exhausted" in low
    if any(k in low for k in _KEY_MARKS):
        return "key"
    # ① 구글이 «어느 한도»인지 이름을 준 경우 — 이게 제일 확실하다. 추측보다 먼저 본다.
    ids = " ".join(_quota_ids(t)).lower()
    if "perday" in ids:
        return "quota_day"
    if "perminute" in ids:
        return "quota_minute"
    # ② 기다려도 안 풀리는 것 (크레딧 0)
    if any(k in low for k in _CREDIT_MARKS):
        return "credits"
    if not is_429 and is_model_gone(t):
        return "model_gone"       # 404는 한도와 아무 상관이 없다
    # ③ 이름이 없으면 글로 짐작 (한도 이름이 있으면 여기까지 오지 않는다)
    if re.search(r"per[\s_]?day|daily limit", low):
        return "quota_day"
    if re.search(r"per[\s_]?minute|requests per minute", low):
        return "quota_minute"
    if is_429:
        return "quota"            # 구글이 자세히 안 알려준 429
    return ""


# 분류 → 화면에 띄울 안내. 「무슨 일인지 + 지금 뭘 하면 되는지」를 한 쌍으로.
_EXPLAIN = {
    "key": ("🔑 제미나이 키가 올바르지 않아요",
            "⚙ 설정에서 키를 다시 넣어 주세요. ai.studio에서 새로 발급한 키를 "
            "공백 없이 붙여넣으면 됩니다."),
    # ⚠ 여기서 «왜» 잔액이 0인지는 단정하지 않는다 — 결제 계정 잔액이 진짜 0일 수도,
    #   이 키의 프로젝트가 결제에 연결이 안 된 것일 수도 있다. 우리가 알 수 있는 건
    #   «이 키로는 못 쓴다»는 것뿐이고, 확인할 곳을 정확히 짚어 주는 게 맞다.
    "credits": ("💳 이 키로는 «선불 크레딧이 0»이라 요청이 막혔어요",
                "기다려도 풀리지 않습니다 — 내일도 똑같아요. "
                "https://ai.studio/projects 에서 ①이 키를 만든 프로젝트가 맞는지 "
                "②그 프로젝트에 결제가 연결돼 있고 잔액이 남아 있는지 확인해 주세요. "
                "후불(pay-as-you-go)로 바꾸면 잔액 때문에 멈추는 일 자체가 없어집니다."),
    "quota_day": ("📅 오늘 쓸 수 있는 «무료 하루 한도»를 다 썼어요",
                  "오늘은 더 눌러도 안 됩니다. 한국시간 오후 4~5시쯤 풀려요. "
                  "지금 꼭 하셔야 하면 ai.studio에서 결제를 켜면 바로 가능합니다."),
    "quota_minute": ("⏱ 1분에 보낼 수 있는 횟수를 잠깐 넘었어요",
                     "잠시 뒤 다시 누르면 됩니다 (컷대장이 먼저 기다렸다 재시도했는데도 "
                     "안 됐어요). 여러 작업을 동시에 돌리고 계시면 하나씩 해 보세요."),
    "quota": ("🚧 제미나이가 «한도 초과»라고 답했어요",
              "하루 한도인지 크레딧인지 구글이 자세히 알려주지 않았어요. "
              "아래 원문을 그대로 보내주시면 정확히 가려 드릴게요."),
    "model_gone": ("🔄 쓰던 AI 모델이 없어져 다른 모델로 바꿔 봤지만 실패했어요",
                   "🪵 로그를 복사해서 보내주세요 — 이 계정이 쓸 수 있는 모델을 "
                   "다시 찾아야 합니다."),
}


def explain_error(text: str) -> dict:
    """실패 원문 → 화면에 그대로 띄울 수 있는 한국어 안내 (v1.28.1).

    `kind`가 빈 값이면 우리가 아는 유형이 아니다 — 부르는 쪽이 원래 글을 쓰면 된다.
    """
    kind = classify_error(text)
    if not kind:
        return {"kind": "", "title": "", "how": "", "raw": "", "quota_ids": [],
                "retry_s": None, "message": ""}
    title, how = _EXPLAIN[kind]
    ids = _quota_ids(text)
    return {
        "kind": kind, "title": title, "how": how,
        "message": google_message(text),
        "quota_ids": ids,
        "retry_s": retry_delay_s(text),
        # 회원님이 [📋 복사]해서 그대로 주실 수 있게 원문도 남긴다 (v1.28.1)
        "raw": str(text or "")[:400],
    }


def error_text(text: str) -> str:
    """안내 한 덩어리 — 화면 한 줄에 넣기 좋은 형태로 (원문·한도 이름 포함)."""
    ex = explain_error(text)
    if not ex["kind"]:
        return ""
    out = f"{ex['title']} — {ex['how']}"
    if ex["quota_ids"]:
        out += f"\n· 걸린 한도: {', '.join(ex['quota_ids'][:3])}"
    if ex["message"]:
        out += f"\n· 구글 원문: {ex['message']}"
    return out


def _key_tail(api_key: str) -> str:
    return (api_key or "")[-8:]


def list_available(api_key: str, timeout: float = 20.0) -> List[str]:
    """이 키로 실제로 쓸 수 있는 모델 이름 목록 (캐시)."""
    tail = _key_tail(api_key)
    with _lock:
        if tail in _avail_cache:
            return list(_avail_cache[tail])
    names: List[str] = []
    try:
        req = urllib.request.Request(
            f"{_BASE}/models?pageSize=200", headers={"x-goog-api-key": api_key})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models") or []:
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            nm = str(m.get("name") or "").split("/")[-1]
            if nm:
                names.append(nm)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, json.JSONDecodeError, KeyError) as e:
        # 목록을 못 받아도 프로그램이 멈추면 안 된다 — 선호 순서로 그냥 시도한다
        log.warning("모델 목록을 못 받았어요 (%s) — 아는 이름으로 시도합니다", str(e)[:120])
        return []
    with _lock:
        _avail_cache[tail] = list(names)
    log.info("제미나이 사용 가능 글 모델 %d개 확인", len(names))
    return names


def _version_key(name: str) -> tuple:
    """이름에서 버전 숫자를 뽑아 최신 우선 정렬용 키를 만든다."""
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", name)] or [0.0]
    return (max(nums), len(name) * -1)


def _pick_from(names: List[str]) -> Optional[str]:
    """목록에서 글 생성에 쓸 만한 것을 직접 고른다 (모르는 새 모델도 잡힌다)."""
    cand = [n for n in names
            if n not in _gone and not any(bad in n.lower() for bad in _NOT_TEXT)]
    if not cand:
        return None
    # 가볍고 싼 flash 계열 우선 → 그다음 버전 높은 순
    flash = [n for n in cand if "flash" in n.lower()]
    pool = flash or cand
    pool.sort(key=_version_key, reverse=True)
    return pool[0]


def resolve_text(want: str, api_key: str) -> str:
    """설정에 적힌 모델(want)을 이 계정이 실제로 쓸 수 있는 이름으로 바꾼다."""
    want = (want or "").strip()
    tail = _key_tail(api_key)
    with _lock:
        hit = _resolved.get((want, tail))
    if hit and hit not in _gone:
        return hit
    names = list_available(api_key)
    chosen = None
    if not names:                       # 목록을 못 받음 → 아는 이름으로라도
        chosen = want if (want and want not in _gone) else next(
            (m for m in TEXT_PREFERENCE if m not in _gone), want)
    else:
        avail = set(names)
        if want and want in avail and want not in _gone:
            chosen = want
        else:
            chosen = next((m for m in TEXT_PREFERENCE
                           if m in avail and m not in _gone), None)
            if not chosen:
                chosen = _pick_from(names)
            if chosen and want and chosen != want:
                log.info("모델 «%s»를 쓸 수 없어 «%s»로 자동 교체했어요", want, chosen)
    chosen = chosen or want or "gemini-flash-latest"
    with _lock:
        _resolved[(want, tail)] = chosen
    return chosen


def _remembered(model: str) -> Optional[str]:
    """이미 «이 이름은 죽었고 대신 이걸 쓴다»고 정해 둔 게 있으면 그것 (조회 없음)."""
    with _lock:
        if model and model not in _gone:
            return None                      # 아직 멀쩡하다고 보고 그대로 쓴다
        for (want, _tail), got in _resolved.items():
            if want == model and got not in _gone:
                return got
    return None


def mark_gone(model: str) -> None:
    """이 이름은 없어졌다고 표시 — 다음부터 안 고른다."""
    if not model:
        return
    with _lock:
        _gone.add(model)
        for k in [k for k, v in _resolved.items() if v == model]:
            _resolved.pop(k, None)
    log.warning("모델 «%s»가 더는 제공되지 않아 다른 모델로 넘어갑니다", model)


_URL_RE = re.compile(r"/models/([^/:]+):([A-Za-z]+)")


def post_url(url: str, payload: dict, api_key: str, *, timeout=None,
             poster=None) -> dict:
    """이미 만들어진 제미나이 URL로 호출 — 모델 부분만 필요할 때 갈아 끼운다.

    poster: 실제로 POST 하는 함수(url, payload, headers, timeout). 호출부가 넘겨주면
    그걸 쓴다 — 테스트가 호출부의 `_http_post_json`을 바꿔치기하는 통로를 막지 않기 위해서.
    """
    m = _URL_RE.search(url or "")
    post = poster or _default_poster()
    if not m:                      # 모양이 다르면 손대지 않고 그대로 (안전)
        return post(url, payload, {"x-goog-api-key": api_key}, **_kw(timeout))
    return post_generate(m.group(1), payload, api_key, method=m.group(2),
                         timeout=timeout, poster=post)


def _default_poster():
    from .tts_engine import _http_post_json  # noqa: PLC0415 — 순환 import 방지

    return _http_post_json


def _kw(timeout) -> dict:
    """timeout을 안 준 호출은 예전처럼 **인자 없이** 부른다.

    호출 모양을 바꾸면 이 함수를 대역으로 바꿔치기해 둔 곳(테스트 등)이 전부 깨진다.
    실제 기본값도 120초라 넘기지 않는 것과 결과가 같다.
    """
    return {} if timeout is None else {"timeout": timeout}


def post_generate(model: str, payload: dict, api_key: str, *,
                  method: str = "generateContent", timeout=None,
                  poster=None) -> dict:
    """글 모델 호출 — 모델이 없어졌을 때만 다른 모델로 갈아타고 한 번 더 시도한다.

    ⚠ 잘 되고 있을 때는 **모델 목록을 조회하지 않는다.** 매번 물어보면
    호출마다 왕복이 한 번씩 더 늘고(느려지고), 키가 없는 환경에서는 멀쩡한 호출까지
    막힌다. 목록은 «없어진 모델»을 실제로 만났을 때만 딱 한 번 본다.
    """
    post = poster or _default_poster()
    use = _remembered(model) or model
    switched = False          # 모델 교체는 딱 한 번
    waits = 0                 # 분당 한도 대기는 최대 두 번
    while True:
        try:
            return post(f"{_BASE}/models/{use}:{method}", payload,
                        {"x-goog-api-key": api_key}, **_kw(timeout))
        except Exception as e:  # noqa: BLE001 — 아는 유형만 걸러내고 나머지는 그대로
            text = getattr(e, "text", "") or str(e)
            if not switched and is_model_gone(text) and classify_error(text) == "model_gone":
                switched = True
                mark_gone(use)
                nxt = resolve_text(model, api_key)   # 이때 처음으로 목록을 본다
                if nxt and nxt != use:
                    use = nxt
                    continue
            # ⏱ v1.28.1 (목록 52): «분당» 한도는 몇 십 초만 쉬면 풀린다. 예전엔 이걸
            #   하루 한도와 똑같이 «크레딧 소진»으로 안내해 회원님이 결제를 의심하셨다.
            #   구글이 알려준 시간만큼 쉬었다 조용히 다시 보낸다.
            if waits < 2 and classify_error(text) == "quota_minute":
                nap = min(float(retry_delay_s(text) or 20.0), 60.0)
                log.warning("분당 한도 — %.0f초 쉬었다 다시 보냅니다 (%d/2)", nap, waits + 1)
                _sleep(nap)
                waits += 1
                continue
            raise
