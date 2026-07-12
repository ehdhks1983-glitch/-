"""웹 UI 서버 E2E — 생성 API → 진행 → 완료 → 영상 서빙(Range)까지 (ffmpeg 필요)."""

import json
import threading
import time
import urllib.parse
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-jobs")
    # 저장 기능이 실제 설정/키 파일을 건드리지 않도록 격리
    iso = tmp_path_factory.mktemp("iso")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"

    httpd = webui.create_server(str(workdir), port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env
    os.environ.pop("GEMINI_API_KEY", None)


def _get(base, path, headers=None):
    # 브라우저 fetch처럼 비ASCII 경로(한글 작업 id)를 퍼센트 인코딩해서 요청
    req = urllib.request.Request(
        base + urllib.parse.quote(path), headers=headers or {}
    )
    return urllib.request.urlopen(req, timeout=30)


def _post(base, path, payload):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(), method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _wait_status(base, job_id, wanted, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = json.loads(_get(base, "/api/state").read())
        job = next((j for j in state["jobs"] if j["id"] == job_id), None)
        if job and job.get("status") in wanted:
            return job
        time.sleep(0.5)
    raise AssertionError(f"{timeout}s 내에 {wanted} 도달 실패")


def test_index_and_state(server):
    html = _get(server, "/").read().decode("utf-8")
    assert "컷대장" in html and "생성 시작" in html
    state = json.loads(_get(server, "/api/state").read())
    assert "jobs" in state and "keys" in state


_SHARED = {}


def test_auto_mode_full_run_and_video_range(server):
    res = _post(server, "/api/generate", {
        "topic": "웹 UI 자동 모드 테스트", "auto": True,
        "script_provider": "stub", "tts_provider": "stub",
    })
    job = _wait_status(server, res["job_id"], {"ok", "partial", "failed"})
    assert job["status"] == "ok", job.get("errors")
    assert job["mp4"]
    _SHARED["done_job"] = job["id"]

    with _get(server, f"/video/{job['id']}", headers={"Range": "bytes=0-99"}) as resp:
        assert resp.status == 206
        assert resp.headers["Content-Type"] == "video/mp4"
        assert resp.headers["Content-Range"].startswith("bytes 0-99/")
        assert len(resp.read()) == 100


def test_review_mode_confirm_flow(server):
    res = _post(server, "/api/generate", {
        "topic": "검토 모드 테스트", "auto": False,
        "script_provider": "stub", "tts_provider": "stub",
    })
    job = _wait_status(server, res["job_id"], {"awaiting_review"})
    assert job["script"]["sentences"]

    _post(server, "/api/confirm", {
        "job_id": job["id"],
        "title": "수정된 제목",
        "sentences": ["검토에서 고친 첫 문장입니다.", "두 번째 문장입니다."],
    })
    done = _wait_status(server, job["id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done["title"] == "수정된 제목"


def test_generate_rejects_empty_topic(server):
    req = urllib.request.Request(
        server + "/api/generate", data=json.dumps({"topic": ""}).encode(), method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_pronounce_endpoint(server):
    data = _post(server, "/api/pronounce", {"lines": ["2026년 AI 트렌드 | AI", "10% 할인"]})
    assert data["lines"] == ["이천이십육년 에이아이 트렌드 | 에이아이", "십퍼센트 할인"]


def test_settings_save_roundtrip(server):
    data = _post(server, "/api/settings", {"settings": {"subtitle": {"font_size": 82}}})
    assert data["ok"]
    state = json.loads(_get(server, "/api/state").read())
    assert state["settings"]["subtitle"]["font_size"] == 82
    assert state["settings"]["subtitle"]["outline"] == 4  # 기본값 유지


def test_key_save_and_clear(server):
    from cutdaejang import config

    _post(server, "/api/generate", {
        "topic": "키 저장 테스트", "auto": True,
        "script_provider": "stub", "tts_provider": "stub",
        "gemini_key": "TEST-KEY-123", "save_key": True,
    })
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if json.loads(_get(server, "/api/state").read())["keys"]["gemini"]:
            break
        time.sleep(0.3)
    assert config.api_keys_path().exists()

    assert _post(server, "/api/keys", {"action": "clear"})["ok"]
    assert not config.api_keys_path().exists()
    assert not json.loads(_get(server, "/api/state").read())["keys"]["gemini"]


def test_regenerate_from_history(server):
    job = _post(server, "/api/regenerate", {"job_id": _SHARED["done_job"]})
    done = _wait_status(server, job["job_id"], {"ok", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done["mp4"] and done["mp4"].endswith(".mp4")


def test_diagnostic_report(server):
    from pathlib import Path

    data = _post(server, "/api/diagnostic", {})
    report = Path(data["path"])
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "컷대장 진단 리포트" in text and "ffmpeg" in text
