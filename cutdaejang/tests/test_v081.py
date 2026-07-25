"""v0.81 — 🔗/🎞 카드 「🎨 꾸미기」(자막·제목 스타일·글씨체·톤) 전달 경로."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_deco_ui_present_and_wired():
    html = webui._HTML
    for tok in ('id="wlDecoBox"', 'id="wlSubStyleSel"', 'id="wlHookStyleSel"',
                'id="wlSubFontSel"', 'id="wlToneSel"',
                'id="secDecoBox"', 'id="secSubStyleSel"', 'id="secHookStyleSel"',
                'id="secSubFontSel"', 'id="secToneSel"', "function cloneSelect"):
        assert tok in html, tok
    # 시작 payload에 스타일 값이 실려 간다
    assert "wlSubStyleSel')||{}).value" in html
    assert "secSubStyleSel')||{}).value" in html
    # 카드 열 때 편집 폼 옵션·기억값 복제
    assert html.count("cloneSelect('editSubStyleSel'") == 2


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v081")
    iso = tmp_path_factory.mktemp("iso81")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"

    httpd = webui.create_server(str(workdir), port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env
    os.environ.pop("GEMINI_API_KEY", None)


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _wait_status(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


@requires_ffmpeg
def test_sections_with_style_override_e2e(server, tmp_path):
    """🎞 구간 1개 + 자막 스타일 지정 → 스타일 파라미터 경로로 정상 완성."""
    from cutdaejang.utils import ffmpeg as ff

    clip = tmp_path / "c.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=purple:s=640x360:r=30:d=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)])
    data = _post(server, "/api/section_edit", {
        "sections": [{"title": "훅", "video_path": str(clip),
                      "narration": "스타일 확인 문장입니다"}],
        "layout": "wide", "quality": "draft",
        "sub_style": "예능 노랑", "hook_style": "기본", "tone": "선명",
    })
    assert data.get("job_id"), data
    done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done.get("mp4")
