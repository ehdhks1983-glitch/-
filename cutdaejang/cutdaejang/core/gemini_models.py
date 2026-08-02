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

_lock = threading.Lock()
_avail_cache: dict = {}       # api_key 뒷자리 → [모델 이름]
_gone: set = set()            # 404를 받은 이름
_resolved: dict = {}          # (want, key꼬리) → 실제로 쓸 이름


def is_model_gone(text: str) -> bool:
    """이 오류가 '모델이 없어졌다'인가 (크레딧·한도 문제와 구분)."""
    t = str(text or "")
    return any(m.lower() in t.lower() for m in _MODEL_GONE_MARKS)


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
    for attempt in (0, 1):
        try:
            return post(f"{_BASE}/models/{use}:{method}", payload,
                        {"x-goog-api-key": api_key}, **_kw(timeout))
        except Exception as e:  # noqa: BLE001 — 모델 문제만 걸러내고 나머지는 그대로
            text = getattr(e, "text", "") or str(e)
            if attempt == 0 and is_model_gone(text):
                mark_gone(use)
                nxt = resolve_text(model, api_key)   # 이때 처음으로 목록을 본다
                if nxt and nxt != use:
                    use = nxt
                    continue
            raise
    raise RuntimeError("모델 선택에 실패했습니다")   # 도달하지 않음
