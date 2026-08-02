"""v1.19 — ✨ AI 영상 클립 생성 + 비용 표시·월 한도 (회원님 요청 24·25번).

> "지금 제작할때 AI모델연결도 넣어야해 시댄스같은거 구간구간마다 필요할때가
>  있떠라구" + "ai로 영상만들때는 얼마정도들어간다는 표시해줘야해"

설계: Veo(기존 제미나이 키 그대로)·fal.ai(시댄스·클링, 선불 크레딧) 2제공자,
구간마다 [✨ AI 클립] 버튼 → 프롬프트 확인 창에 **예상 요금(원)** → 생성 후
클립 칸 자동 입력. 완료 시 예상액을 월 누적에 더하고, 한도를 넘으면 잠긴다.
같은 (제공자·모델·프롬프트·길이) 조합은 캐시를 재사용해 **과금이 없다**.
여기 테스트는 전부 가짜 HTTP — 실 API 과금 없이 흐름을 검증한다.
"""

import io
import json
import threading
import time
import urllib.error
import urllib.request

from cutdaejang import __version__, config
from cutdaejang.core import video_gen
from cutdaejang.gui import webui


def test_version():
    assert __version__ == "1.25.0"


# ── 설정·키 배선 ─────────────────────────────────────────────────
def test_config_ai_defaults_and_fal_key():
    ai = config.DEFAULTS["ai"]
    assert ai["video_provider"] == "veo"
    assert "veo" in ai["won_per_s"] and "fal" in ai["won_per_s"]
    assert ai["monthly_limit_won"] > 0          # 기본은 한도 있음 (과금 사고 방지)
    assert ai["spent_won"] == {}
    assert config._KEY_ENVS["fal"] == "FAL_API_KEY"


# ── find_video_url — 응답 어디에 있든 영상 주소를 찾는다 ─────────
def test_find_video_url_prefers_mp4():
    obj = {"a": "https://x.example/thumb.png",
           "b": {"c": ["https://x.example/out.mp4?sig=1"]}}
    assert video_gen.find_video_url(obj).endswith("out.mp4?sig=1")
    assert video_gen.find_video_url({"u": "https://x.example/video/123"}) \
        == "https://x.example/video/123"
    assert video_gen.find_video_url({"u": "https://x.example/page"}) \
        == "https://x.example/page"              # 폴백: 첫 http 주소
    assert video_gen.find_video_url({}) == ""


def test_clip_cache_path_is_stable_and_prompt_sensitive(tmp_path):
    a = video_gen.clip_cache_path(tmp_path, "veo", "m", "드론 샷", 5, "720p")
    b = video_gen.clip_cache_path(tmp_path, "veo", "m", "드론 샷", 5, "720p")
    c = video_gen.clip_cache_path(tmp_path, "veo", "m", "고양이", 5, "720p")
    assert a == b and a != c
    assert a.parent.name == "ai_clips"


# ── 가짜 HTTP 도우미 ─────────────────────────────────────────────
class _Resp:
    def __init__(self, payload):
        self._p = payload if isinstance(payload, bytes) \
            else json.dumps(payload).encode("utf-8")

    def read(self, n=None):
        if n is None:
            out, self._p = self._p, b""
        else:
            out, self._p = self._p[:n], self._p[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, body=b"bad"):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body))


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"v" * 40_000   # 30KB 하한 통과


# ── Veo — 접수→폴링→다운로드 (가짜 HTTP, 과금 없음) ──────────────
def test_veo_full_flow(tmp_path, monkeypatch):
    calls = []

    def fake(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append((url, req.data if hasattr(req, "data") else None))
        if ":predictLongRunning" in url:
            body = json.loads(req.data)
            assert body["instances"][0]["prompt"] == "밤의 드론 샷"
            assert body["parameters"]["durationSeconds"] == 5
            return _Resp({"name": "operations/abc"})
        if "/operations/abc" in url:
            if len([c for c in calls if "/operations/" in c[0]]) == 1:
                return _Resp({"done": False})
            return _Resp({"done": True, "response": {
                "generateVideoResponse": {"generatedSamples": [
                    {"video": {"uri": "https://dl.example/v.mp4"}}]}}})
        if url == "https://dl.example/v.mp4":
            return _Resp(MP4)
        raise AssertionError("예상 밖 호출: " + url)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    path, cached = video_gen.generate_clip(
        "밤의 드론 샷", "veo", "KEY", tmp_path, model="veo-test", duration_s=5)
    assert not cached
    assert path.endswith(".mp4")
    import pathlib
    assert pathlib.Path(path).stat().st_size == len(MP4)


def test_veo_retries_with_minimal_params_on_400(tmp_path, monkeypatch):
    posts = []

    def fake(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if ":predictLongRunning" in url:
            posts.append(json.loads(req.data))
            if len(posts) == 1:                 # 인자 이름 거부 → 최소 인자 재시도
                raise _http_error(400, b"unknown parameter durationSeconds")
            return _Resp({"name": "operations/r"})
        if "/operations/r" in url:
            return _Resp({"done": True,
                          "response": {"video": "https://dl.example/r.mp4"}})
        if url == "https://dl.example/r.mp4":
            return _Resp(MP4)
        raise AssertionError(url)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    path, cached = video_gen.generate_clip("샷", "veo", "KEY", tmp_path)
    assert not cached and len(posts) == 2
    assert set(posts[1]["parameters"]) == {"aspectRatio"}   # 최소 인자만


# ── fal.ai — 큐 접수→상태 폴링→결과 (시댄스·클링 계열) ───────────
def test_fal_queue_flow_and_422_fallback(tmp_path, monkeypatch):
    posts, stat = [], {"n": 0}

    def fake(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/text-to-video") and req.data:
            posts.append(json.loads(req.data))
            assert req.get_header("Authorization") == "Key FKEY"
            if len(posts) == 1:                 # 모델별 인자 차이 → 최소 재시도
                raise _http_error(422, b"unexpected field resolution")
            return _Resp({"request_id": "r1",
                          "status_url": "https://q.example/st",
                          "response_url": "https://q.example/res"})
        if url == "https://q.example/st":
            stat["n"] += 1
            return _Resp({"status": "IN_PROGRESS" if stat["n"] == 1
                          else "COMPLETED"})
        if url == "https://q.example/res":
            return _Resp({"video": {"url": "https://cdn.example/o.mp4"}})
        if url == "https://cdn.example/o.mp4":
            return _Resp(MP4)
        raise AssertionError(url)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    path, cached = video_gen.generate_clip(
        "고양이", "fal", "FKEY", tmp_path,
        model="fal-ai/bytedance/seedance/v1/lite/text-to-video")
    assert not cached and path.endswith(".mp4")
    assert list(posts[1]) == ["prompt"]         # 재시도는 prompt만


# ── ♻ 캐시 재사용 — 네트워크 호출 자체가 없다 = 과금 0 ──────────
def test_cache_hit_makes_no_network_call(tmp_path, monkeypatch):
    dest = video_gen.clip_cache_path(tmp_path, "veo", "m", "같은 장면", 5, "720p")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(MP4)

    def boom(*a, **k):
        raise AssertionError("캐시가 있는데 네트워크를 불렀다 — 과금 위험!")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    path, cached = video_gen.generate_clip("같은 장면", "veo", "KEY", tmp_path,
                                           model="m", duration_s=5)
    assert cached and path == str(dest)


# ── 서버 라우트 — /api/ai_cost · /api/gen_clip ───────────────────
import pytest  # noqa: E402


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    workdir = tmp_path_factory.mktemp("v119-jobs")
    iso = tmp_path_factory.mktemp("iso119")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(workdir), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), 200
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read())


def _wait_job(base, job_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _get(base, "/api/state")
        j = next((x for x in st.get("jobs", []) if x.get("id") == job_id), {})
        if j.get("status") in {"ok", "failed"}:
            return j
        time.sleep(0.2)
    raise AssertionError("작업 미완료")


def test_ai_cost_route_shape(server, monkeypatch):
    monkeypatch.delenv("FAL_API_KEY", raising=False)
    d = _get(server, "/api/ai_cost")
    assert d["ok"] and d["provider"] in ("veo", "fal")
    assert "veo" in d["won_per_s"] and "fal" in d["won_per_s"]
    assert isinstance(d["monthly_limit_won"], int)
    assert isinstance(d["spent_won"], int)
    assert d["has_fal"] is False and isinstance(d["has_gemini"], bool)


def test_gen_clip_requires_prompt(server):
    d, code = _post(server, "/api/gen_clip", {})
    assert code == 400 and "프롬프트" in d["error"]


def test_gen_clip_blocks_over_monthly_limit(server):
    month = time.strftime("%Y-%m")
    config.save_settings({"ai": {"monthly_limit_won": 1000,
                                 "won_per_s": {"veo": 210},
                                 "spent_won": {month: 900}}})
    try:
        d, code = _post(server, "/api/gen_clip",
                        {"prompt": "드론 샷", "provider": "veo",
                         "duration_s": 5})     # 900 + 1050 > 1000 → 잠금
        assert code == 400
        assert "한도" in d["error"] and "예상치" in d["error"]
        assert "⚙설정" in d["error"]           # 어디서 푸는지 안내
    finally:
        config.save_settings({"ai": {"monthly_limit_won": 10000,
                                     "spent_won": {month: 0}}})


def test_gen_clip_requires_provider_key(server, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("FAL_API_KEY", raising=False)
    d, code = _post(server, "/api/gen_clip", {"prompt": "샷", "provider": "veo"})
    assert code == 400 and "제미나이" in d["error"]
    d, code = _post(server, "/api/gen_clip", {"prompt": "샷", "provider": "fal"})
    assert code == 400 and "fal.ai" in d["error"] and "선불" in d["error"]


def test_gen_clip_job_accumulates_estimated_spend(server, tmp_path, monkeypatch):
    """완료되면 예상액이 월 누적에 더해지고, 캐시 재사용이면 더하지 않는다."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    clip = tmp_path / "made.mp4"
    clip.write_bytes(MP4)
    monkeypatch.setattr(video_gen, "generate_clip",
                        lambda *a, **k: (str(clip), False))
    month = time.strftime("%Y-%m")
    base_spent = int(((config.load_settings().get("ai") or {})
                      .get("spent_won") or {}).get(month) or 0)
    d, code = _post(server, "/api/gen_clip",
                    {"prompt": "드론 샷", "provider": "veo", "duration_s": 5})
    assert code == 200 and d["est_won"] > 0
    job = _wait_job(server, d["job_id"])
    assert job["status"] == "ok" and job["clip"] == str(clip)
    assert "예상치" in job["note"]              # 25번: 완료 표시도 예상치 명시
    spent = ((config.load_settings().get("ai") or {}).get("spent_won") or {})
    assert int(spent.get(month) or 0) == base_spent + d["est_won"]

    # ♻ 캐시 재사용 — 누적이 늘지 않는다
    monkeypatch.setattr(video_gen, "generate_clip",
                        lambda *a, **k: (str(clip), True))
    d2, _ = _post(server, "/api/gen_clip",
                  {"prompt": "드론 샷", "provider": "veo", "duration_s": 5})
    job2 = _wait_job(server, d2["job_id"])
    assert job2["status"] == "ok" and "과금 없음" in job2["note"]
    spent2 = ((config.load_settings().get("ai") or {}).get("spent_won") or {})
    assert int(spent2.get(month) or 0) == base_spent + d["est_won"]


# ── 화면 배선 ────────────────────────────────────────────────────
def test_ui_wiring_tokens():
    html = webui._apply_links(webui._HTML)
    for tok in ("aiClipBox", "aiClipPrompt", "aiClipEstLine", "aiClipGo",
                "sec-ai", "✨ AI 클립", "aiSpendLine", "apiFalKey",
                "saveApiKey(event,'fal')", "setAiProv", "setVeoModel",
                "setFalModel", "setWonVeo", "setWonFal", "setAiLimit",
                "예상 요금", "과금이 없어요", "선불 크레딧",
                "ai_clip:'✨ AI 클립 생성"):
        assert tok in html, tok
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert '("fal_key", "FAL_API_KEY", "fal")' in src
    assert "def _run_gen_clip" in src
    assert src.count('"fal": bool(os.environ.get("FAL_API_KEY"))') >= 2
