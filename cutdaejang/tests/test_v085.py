"""v0.85 — 히스토리 누락 수정 + 다시 편집(부분 재제작) + 임시 저장 + 전환 다양화."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v085_ui_present_and_wired():
    html = webui._HTML
    for tok in ('id="secXfadeSel"', "다양하게", 'value="none"',
                "function saveSecDraft", "function clearSecDraft",
                "function fillSectionsForm", "function reEditSections",
                "/api/sec_draft", "/api/job_params", "reuse_job",
                'id="secDraftHint"', "has_params", "다시 편집"):
        assert tok in html, tok


def test_record_simple_history_strips_secrets(tmp_path):
    from cutdaejang.db.jobs import JobStore

    webui._record_simple_history(
        str(tmp_path), "hist85", title="🎞 테스트", mode="sections", status="ok",
        mp4=None, params={"sections": [{"narration": "가"}], "gemini_key": "비밀",
                          "save_key": True, "layout": "wide"})
    store = JobStore(tmp_path / "history.db")
    row = store.get("hist85")
    store.close()
    assert row and row["mode"] == "sections" and row["title"] == "🎞 테스트"
    saved = json.loads(row["params_json"])
    assert saved["layout"] == "wide" and saved["sections"]
    assert "gemini_key" not in saved and "save_key" not in saved


@requires_ffmpeg
def test_concat_transition_varied_and_named(tmp_path):
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    clips = []
    for i, c in enumerate(["red", "green", "blue"]):
        p = tmp_path / f"c{i}.mp4"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={c}:s=320x240:r=30:d=4",
                "-f", "lavfi", "-i", "sine=frequency=400:duration=4",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(p)])
        clips.append(str(p))
    # 🎲 다양하게 — 경계 2곳이 서로 다른 전환으로 (12 - 2*0.4 ≈ 11.2초)
    out = video_editor.concat_videos(clips, str(tmp_path / "v.mp4"),
                                     crossfade_s=0.4, transition="varied")
    assert 10.7 <= ff.probe_duration_us(out) / 1e6 <= 11.8
    # 이름 지정 전환 (밀어내기)
    out2 = video_editor.concat_videos(clips[:2], str(tmp_path / "s.mp4"),
                                      crossfade_s=0.4, transition="slideleft")
    assert 7.2 <= ff.probe_duration_us(out2) / 1e6 <= 7.9


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v085")
    iso = tmp_path_factory.mktemp("iso85")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"

    httpd = webui.create_server(str(workdir), port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", str(workdir)
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
        with urllib.request.urlopen(req, timeout=60) as r:
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


def _mk_clip(tmp_path, name, color, sec=4):
    from cutdaejang.utils import ffmpeg as ff

    p = tmp_path / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d={sec}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(p)])
    return str(p)


@requires_ffmpeg
def test_sections_history_reedit_and_partial_rebuild_e2e(server, tmp_path):
    """완성 → 히스토리 기록·job_params 회수 → 재실행 시 안 바뀐 구간 재사용."""
    base, workdir = server
    a = _mk_clip(tmp_path, "a.mp4", "red")
    b = _mk_clip(tmp_path, "b.mp4", "blue")
    secs = [
        {"title": "도입", "video_path": a, "narration": "첫 구간 문장입니다"},
        {"title": "정리", "video_path": b, "narration": "둘째 구간 문장이에요"},
    ]
    d1 = _post(base, "/api/section_edit",
               {"sections": secs, "layout": "wide", "quality": "draft"})
    assert d1.get("job_id"), d1
    done1 = _wait_status(base, d1["job_id"], {"ok", "partial", "failed"})
    assert done1["status"] == "ok", done1.get("errors")

    # 📜 히스토리에 남았다 (프로그램 재시작 후에도 보임 — history.db)
    from cutdaejang.db.jobs import JobStore
    from pathlib import Path
    store = JobStore(Path(workdir) / "history.db")
    row = store.get(d1["job_id"])
    store.close()
    assert row and row["mode"] == "sections" and row["out_mp4"]
    assert row["params_json"] and "gemini_key" not in row["params_json"]

    # ✏ 다시 편집 — 저장된 입력값 회수
    dp = _post(base, "/api/job_params", {"job_id": d1["job_id"]})
    assert dp.get("ok") and dp["mode"] == "sections", dp
    assert len(dp["params"]["sections"]) == 2
    assert dp["params"]["sections"][0]["narration"] == "첫 구간 문장입니다"

    # ♻ 같은 입력 + reuse_job → 두 구간 모두 재사용
    d2 = _post(base, "/api/section_edit",
               {"sections": secs, "layout": "wide", "quality": "draft",
                "reuse_job": d1["job_id"]})
    done2 = _wait_status(base, d2["job_id"], {"ok", "partial", "failed"})
    assert done2["status"] == "ok", done2.get("errors")
    assert "안 바뀐 2구간" in (done2.get("tts_warn") or ""), done2.get("tts_warn")

    # ♻ 한 구간만 수정 → 그 구간만 재제작 (1구간 재사용)
    secs2 = [dict(secs[0]),
             {**secs[1], "narration": "둘째 구간을 고친 문장이에요"}]
    d3 = _post(base, "/api/section_edit",
               {"sections": secs2, "layout": "wide", "quality": "draft",
                "reuse_job": d2["job_id"]})
    done3 = _wait_status(base, d3["job_id"], {"ok", "partial", "failed"})
    assert done3["status"] == "ok", done3.get("errors")
    assert "안 바뀐 1구간" in (done3.get("tts_warn") or ""), done3.get("tts_warn")


@requires_ffmpeg
def test_sec_draft_roundtrip(server):
    base, _ = server
    draft = {"src_mode": "clips", "layout": "shorts",
             "sections": [{"title": "훅", "narration": "임시 저장 문장",
                           "video_path": "", "speed": "", "start": "", "end": ""}]}
    d = _post(base, "/api/sec_draft", {"draft": draft})
    assert d.get("ok"), d
    with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
        st = json.loads(r.read())
    saved = ((st.get("settings") or {}).get("ui") or {}).get("sec_draft")
    assert saved and saved["sections"][0]["narration"] == "임시 저장 문장"
    d2 = _post(base, "/api/sec_draft", {"clear": True})
    assert d2.get("ok")
    with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
        st2 = json.loads(r.read())
    assert not ((st2.get("settings") or {}).get("ui") or {}).get("sec_draft")
