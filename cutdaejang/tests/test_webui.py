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


def test_beginner_ui_structure(server):
    """v0.36 초보자 UI: 홈 카드 3개 + 단계형 폼 + 접는 옵션 그룹 (옛 토글 잔재 없음)."""
    html = _get(server, "/").read().decode("utf-8")
    assert 'id="homeCard"' in html
    assert html.count('class="modecard"') == 3  # AI 영상/내 영상 편집/사진
    # 완전 자동은 이제 라디오(editFinish) + 길이 프리셋으로
    assert 'name="editFinish"' in html and 'id="autoTargetPreset"' in html
    # 꾸미기 그룹: 훅·내레이션·소리·워터마크·대본·세부설정
    for gid in ("optHook", "optNarr", "optSound", "optWm", "optScript", "optAdv"):
        assert f'id="{gid}"' in html, gid
    # 이전 UI 잔재가 남아 있으면 안 됨 (appmode 라디오·완전자동 체크박스)
    assert "appmode" not in html and "autoEditChk" not in html
    # 사진 모드 블록 분리
    assert 'id="videoBlock"' in html and 'id="photoBlock"' in html


def test_my_voice_card_structure(server):
    """v0.37 내 목소리 전용 화면: 진입 3경로(홈/생성 폼/내레이션) + 등록 폼 + 상태 표시."""
    html = _get(server, "/").read().decode("utf-8")
    assert 'id="voiceCard"' in html
    # 등록 UI는 전용 화면 한 곳에만 (sovits/clone 입력이 중복되면 id 충돌)
    for fid in ("sovitsRef", "sovitsRefText", "cloneFile", "elevenKey"):
        assert html.count(f'id="{fid}"') == 1, fid
    # 바로가기 버튼 3곳: 홈 + AI 생성 폼 + 내레이션 그룹
    assert html.count("openVoice(event)") >= 3
    # 등록 상태 표시 3곳
    for sid in ("myVoiceState", "myVoiceStateNarr", "homeVoiceState"):
        assert f'id="{sid}"' in html, sid
    # 방법별 미리듣기
    assert "previewMyVoice(event,'sovits')" in html
    assert "previewMyVoice(event,'elevenlabs')" in html
    # v0.38: 완전 자동 — 여러 개 나누기 + 화질 + 세팅 기억 복원
    assert 'id="autoMultiSel"' in html and 'id="autoQualitySel"' in html
    assert "applyEditLast" in html


def test_auto_multi_split_and_settings_remembered(server, tmp_path):
    """v0.38: 완전 자동 '여러 개로 나누기'(자막 없음 → 시간 균등 분할) + 폼 세팅 기억."""
    import os
    from pathlib import Path

    video = _make_talk_video(tmp_path / "long.mp4")  # 5.5초 → 2초 단위 = 쇼츠 2~3개
    data = _post(server, "/api/edit", {
        "video_path": video, "layout": "shorts",
        "auto_subtitle": False, "cut_silence": False,
        "auto_edit": True, "auto_multi": True, "auto_target_sec": 2,
        "speed": 1, "quality": "draft", "orig_audio": "keep",
        "denoise": "", "bgm": "", "bgm_db": -14, "hook_scale": 1.2,
    })
    job = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=240)
    assert job["status"] == "ok", job.get("errors")
    outs = job.get("mp4s") or []
    assert len(outs) >= 2 and all(o.endswith(".mp4") for o in outs)
    assert "쇼츠" in (job.get("note") or "")
    # 폼 세팅이 기억됐는지 (다음 실행 때 화면 자동 복원용)
    saved = json.loads(Path(os.environ["CUTDAEJANG_SETTINGS"]).read_text(encoding="utf-8"))
    last = saved.get("ui", {}).get("edit_last", {})
    assert last.get("auto_edit") is True and last.get("auto_multi") is True
    assert last.get("auto_target_sec") == 2 and last.get("quality") == "draft"
    # 작업별 입력·키는 기억하지 않음
    assert "video_path" not in last and "gemini_key" not in last and "hook" not in last
    # /api/state 로도 노출 (브라우저가 이걸 읽어 폼을 채움)
    state = json.loads(_get(server, "/api/state").read())
    assert state["settings"]["ui"]["edit_last"]["auto_multi"] is True


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


def test_pick_file_returns_selected_path(server):
    from cutdaejang.gui import webui

    orig = webui.pick_video_file
    webui.pick_video_file = lambda timeout=600.0: "C:\\Users\\나\\Videos\\clip.mp4"
    try:
        data = _post(server, "/api/pick_file", {})
        assert data["path"] == "C:\\Users\\나\\Videos\\clip.mp4"
        assert data["cancelled"] is False
    finally:
        webui.pick_video_file = orig


def test_pick_file_cancelled(server):
    from cutdaejang.gui import webui

    orig = webui.pick_video_file
    webui.pick_video_file = lambda timeout=600.0: None  # 사용자가 취소
    try:
        data = _post(server, "/api/pick_file", {})
        assert data["path"] == "" and data["cancelled"] is True
    finally:
        webui.pick_video_file = orig


def test_pick_file_unavailable_returns_error(server):
    from cutdaejang.gui import webui

    orig = webui.pick_video_file

    def _raise(timeout=600.0):
        raise RuntimeError("파일 선택 창을 열 수 없습니다")

    webui.pick_video_file = _raise
    try:
        req = urllib.request.Request(
            server + "/api/pick_file", data=b"{}", method="POST"
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 500
    finally:
        webui.pick_video_file = orig


def _make_talk_video(path):
    from cutdaejang.utils import ffmpeg as ff

    audio = str(path) + ".wav"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=2:sample_rate=44100",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=2:sample_rate=44100",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[a]", "-map", "[a]", audio,
    ])
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=navy:s=720x1280:r=30:d=5.5",
        "-i", audio, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(path),
    ])
    return str(path)


def test_edit_two_phase_review_and_render(server, tmp_path):
    video = _make_talk_video(tmp_path / "talk.mp4")
    # 1단계: 분석 → 자막 검토 대기
    res = _post(server, "/api/edit", {
        "video_path": video, "layout": "shorts",
        "stt_provider": "stub", "auto_subtitle": True,
    })
    job = _wait_status(server, res["job_id"], {"review_subtitle", "failed"})
    assert job["status"] == "review_subtitle", job.get("errors")
    subs = job["subtitles"]
    assert len(subs) >= 1

    # 자막 수정 후 렌더
    subs[0]["text"] = "웹 검토에서 고친 자막"
    _post(server, "/api/edit_render", {"job_id": job["id"], "subtitles": subs, "hook": "훅"})
    done = _wait_status(server, job["id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done["mp4"]


def test_diagnostic_report(server):
    from pathlib import Path

    data = _post(server, "/api/diagnostic", {})
    report = Path(data["path"])
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "컷대장 진단 리포트" in text and "ffmpeg" in text
