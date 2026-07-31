"""✨ AI 영상 클립 생성 (v1.19, 목록 24·25) — 구간에 끼울 짧은 클립을 텍스트로.

제공자 2종 — 둘 다 표준 REST + 폴링, 표준 라이브러리만:
  · veo — 구글 Gemini API(기존 키 그대로). predictLongRunning → 작업 폴링 → 파일
  · fal — fal.ai 큐 API(선불 크레딧 = 충전한 만큼만). 모델 주소는 설정에서 교체
    가능해 시댄스·클링 등 무엇이든 연결된다.

같은 (제공자·모델·프롬프트·길이·해상도) 조합은 ai_clips/ 캐시를 재사용해
**과금이 없다**. 프롬프트는 확인 창에서 회원이 보고 승인한 것만 보낸다.
제공자 API의 인자 이름은 버전마다 달라질 수 있어, 인자 거부(400/422)면
최소 인자(prompt만)로 1회 재시도한다 — 모델 주소만 맞으면 웬만하면 돈다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Tuple

log = logging.getLogger("cutdaejang")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
FAL_QUEUE = "https://queue.fal.run"


class VideoGenError(RuntimeError):
    """사용자에게 그대로 보여줄 한국어 메시지."""


def _req_json(url: str, payload=None, headers: Optional[dict] = None,
              timeout: float = 30.0) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise VideoGenError(f"HTTP {e.code}: {body}") from e


def _collect_urls(obj, out: list) -> None:
    if isinstance(obj, str):
        if obj.startswith("http"):
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_urls(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_urls(v, out)


def find_video_url(obj) -> str:
    """응답 어디에 있든 영상 URL을 찾는다 — 제공자·버전마다 위치가 달라서.

    .mp4 나 'video'가 들어간 주소를 우선하고, 없으면 첫 번째 http 주소.
    """
    urls: list = []
    _collect_urls(obj, urls)
    for u in urls:
        low = u.lower()
        if ".mp4" in low or "video" in low:
            return u
    return urls[0] if urls else ""


def _download(url: str, dest: Path, headers: Optional[dict] = None,
              timeout: float = 180.0) -> None:
    req = urllib.request.Request(url, headers=headers or {})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
    if tmp.stat().st_size < 30_000:
        tmp.unlink(missing_ok=True)
        raise VideoGenError("받은 영상 파일이 비정상적으로 작아요 — 다시 시도해 주세요")
    tmp.replace(dest)


def clip_cache_path(workdir, provider: str, model: str, prompt: str,
                    duration_s: int, resolution: str) -> Path:
    key = json.dumps([provider, model, (prompt or "").strip(),
                      int(duration_s), resolution], ensure_ascii=False)
    name = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".mp4"
    return Path(workdir) / "ai_clips" / name


def _veo(prompt: str, api_key: str, model: str, duration_s: int, resolution: str,
         aspect: str, say: Callable, timeout_s: float) -> Tuple[str, dict]:
    model = model or "veo-3.1-fast-generate-001"
    hdr = {"x-goog-api-key": api_key}
    say(f"✨ Veo({model})에 생성을 요청했어요…")
    full = {"instances": [{"prompt": prompt}],
            "parameters": {"aspectRatio": aspect, "resolution": resolution,
                           "durationSeconds": int(duration_s)}}
    try:
        op = _req_json(f"{GEMINI_BASE}/models/{model}:predictLongRunning",
                       full, hdr, timeout=60)
    except VideoGenError as e:
        msg = str(e)
        if "HTTP 400" in msg or "HTTP 404" in msg:
            # 인자 이름이 버전마다 달라 거부될 수 있다 → 최소 인자로 1회 재시도.
            # 404는 모델 이름 문제일 가능성이 커 안내를 덧붙인다.
            if "HTTP 404" in msg:
                raise VideoGenError(
                    f"모델을 찾지 못했어요({model}) — ⚙설정 「AI 클립 생성」의 "
                    "Veo 모델 이름을 확인해 주세요") from e
            op = _req_json(f"{GEMINI_BASE}/models/{model}:predictLongRunning",
                           {"instances": [{"prompt": prompt}],
                            "parameters": {"aspectRatio": aspect}}, hdr, timeout=60)
        else:
            raise
    name = str(op.get("name") or "")
    if not name:
        raise VideoGenError("생성 접수에 실패했어요 (응답에 작업 이름이 없음)")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(5)
        st = _req_json(f"{GEMINI_BASE}/{name}", None, hdr, timeout=30)
        if st.get("error"):
            raise VideoGenError(
                "생성 실패: " + json.dumps(st["error"], ensure_ascii=False)[:200])
        if st.get("done"):
            url = find_video_url(st.get("response"))
            if not url:
                raise VideoGenError("완료됐지만 영상 주소를 찾지 못했어요")
            return url, hdr
        say("✨ Veo가 영상을 만드는 중… (보통 1~5분 — 멈춘 게 아니에요)")
    raise VideoGenError("생성이 너무 오래 걸려 중단했어요 — 잠시 후 다시 시도해 주세요")


def _fal(prompt: str, api_key: str, model: str, duration_s: int, resolution: str,
         aspect: str, say: Callable, timeout_s: float) -> Tuple[str, dict]:
    model = (model or "fal-ai/bytedance/seedance/v1/lite/text-to-video").strip("/")
    hdr = {"Authorization": f"Key {api_key}"}
    say(f"✨ fal.ai({model})에 생성을 요청했어요…")
    body = {"prompt": prompt, "aspect_ratio": aspect,
            "resolution": resolution, "duration": str(int(duration_s))}
    try:
        sub = _req_json(f"{FAL_QUEUE}/{model}", body, hdr, timeout=60)
    except VideoGenError as e:
        msg = str(e)
        if "HTTP 404" in msg:
            raise VideoGenError(
                f"모델 주소를 찾지 못했어요({model}) — fal.ai 사이트에서 모델 "
                "페이지의 주소(fal-ai/…)를 복사해 ⚙설정 「AI 클립 생성」에 "
                "넣어주세요") from e
        if "HTTP 400" in msg or "HTTP 422" in msg:
            sub = _req_json(f"{FAL_QUEUE}/{model}", {"prompt": prompt}, hdr,
                            timeout=60)   # 모델별 인자 차이 → 최소 인자 재시도
        else:
            raise
    rid = str(sub.get("request_id") or "")
    status_url = str(sub.get("status_url")
                     or f"{FAL_QUEUE}/{model}/requests/{rid}/status")
    resp_url = str(sub.get("response_url")
                   or f"{FAL_QUEUE}/{model}/requests/{rid}")
    if not rid and "request_id" not in sub:
        # 큐를 안 쓰는 모델이면 응답에 바로 영상이 실려 온다
        url = find_video_url(sub)
        if url:
            return url, {}
        raise VideoGenError("생성 접수에 실패했어요 (요청 번호 없음)")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(4)
        st = _req_json(status_url, None, hdr, timeout=30)
        status = str(st.get("status") or "").upper()
        if status == "COMPLETED":
            res = _req_json(resp_url, None, hdr, timeout=60)
            url = find_video_url(res)
            if not url:
                raise VideoGenError("완료됐지만 영상 주소를 찾지 못했어요")
            return url, {}                    # fal 결과 파일은 공개 CDN — 인증 불필요
        if status in ("FAILED", "CANCELLED", "ERROR"):
            raise VideoGenError("생성 실패: " + json.dumps(st, ensure_ascii=False)[:200])
        say("✨ 영상을 만드는 중… (보통 1~5분 — 멈춘 게 아니에요)")
    raise VideoGenError("생성이 너무 오래 걸려 중단했어요 — 잠시 후 다시 시도해 주세요")


def generate_clip(prompt: str, provider: str, api_key: str, workdir,
                  model: str = "", duration_s: int = 5, resolution: str = "720p",
                  aspect: str = "16:9",
                  progress_cb: Optional[Callable[[str], None]] = None,
                  timeout_s: float = 420.0) -> Tuple[str, bool]:
    """클립 1개 생성 → (파일 경로, 캐시 재사용 여부). 실패는 VideoGenError."""
    say = progress_cb or (lambda m: None)
    prompt = (prompt or "").strip()
    if not prompt:
        raise VideoGenError("어떤 장면인지 프롬프트를 적어주세요")
    if not api_key:
        raise VideoGenError("API 키가 없어요 — 🔑 API 연동에서 넣어주세요")
    dest = clip_cache_path(workdir, provider, model, prompt, duration_s, resolution)
    if dest.is_file() and dest.stat().st_size > 30_000:
        say("♻ 같은 프롬프트로 만들어 둔 클립을 재사용해요 (과금 없음)")
        return str(dest), True
    if provider == "veo":
        url, hdr = _veo(prompt, api_key, model, duration_s, resolution,
                        aspect, say, timeout_s)
    elif provider == "fal":
        url, hdr = _fal(prompt, api_key, model, duration_s, resolution,
                        aspect, say, timeout_s)
    else:
        raise VideoGenError(f"모르는 제공자예요: {provider}")
    say("⬇ 완성된 클립을 받는 중…")
    _download(url, dest, headers=hdr)
    log.info("✨ AI 클립 생성: %s (%s, %ss)", dest.name, provider, duration_s)
    return str(dest), False
