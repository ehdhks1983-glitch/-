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


def test_upload_kit_stub_and_file(server, tmp_path):
    """v0.39 업로드 키트: 키 없이 스텁 생성 + 업로드킷.txt 저장 + 체크리스트/구성 검증."""
    from pathlib import Path

    video = _make_talk_video(tmp_path / "kit.mp4")
    data = _post(server, "/api/edit", {
        "video_path": video, "layout": "shorts",
        "auto_subtitle": False, "cut_silence": False,
        "auto_edit": True, "auto_target_sec": 0,
        "script": "업로드 키트 테스트 문장입니다\n두 번째 문장입니다",
        "bgm": "", "hook": "테스트 훅 제목",
    })
    job = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=240)
    assert job["status"] == "ok", job.get("errors")

    kit_res = _post(server, "/api/upload_kit", {"job_id": data["job_id"]})
    assert kit_res.get("stub") is True  # 키 없음 → 예시 문구
    kit = kit_res["kit"]
    assert len(kit["titles"]) >= 3 and kit["description"].strip()
    assert len(kit["keywords"]) == 10 and len(kit["hashtags"]) == 3
    assert kit["category"]  # 카테고리 항상 존재
    assert any("쇼츠" in c or "세로" in c for c in kit["checklist"])  # 쇼츠 자동 인식 안내
    # 파일 저장 확인
    assert kit_res["path"].endswith("업로드킷.txt")
    saved = Path(kit_res["path"]).read_text(encoding="utf-8")
    assert "제목 후보" in saved and "태그" in saved and "카테고리" in saved


def test_upload_kit_requires_finished_video(server):
    import urllib.error

    req = urllib.request.Request(
        server + "/api/upload_kit",
        data=json.dumps({"job_id": "없는작업"}).encode(), method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


_SHARED = {}


def test_auto_mode_full_run_and_video_range(server):
    res = _post(server, "/api/generate", {
        "topic": "웹 UI 자동 모드 테스트", "auto": True,
        "script_provider": "stub", "tts_provider": "stub",
    })
    job = _wait_status(server, res["job_id"], {"ok", "partial", "failed"})
    assert job["status"] == "ok", job.get("errors")
    assert job["mp4"]
    # v0.40: 어떤 배경이 쓰였는지 완료 화면에 표시 (여기선 설정 꺼짐 → 기본 그라데이션+사유)
    assert "기본 그라데이션" in job.get("bg_source", "") and "꺼짐" in job["bg_source"]
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


def test_edit_render_with_trim_and_vrew_delete(server, tmp_path):
    """v0.41: 앞뒤 트림 + keep 재매핑 — 5.5초 영상을 1~4초만 사용해 완성."""
    from pathlib import Path
    from cutdaejang.utils import ffmpeg as ff

    video = _make_talk_video(tmp_path / "trim.mp4")  # 5.5초
    data = _post(server, "/api/edit", {
        "video_path": video, "layout": "keep",
        "auto_subtitle": True, "cut_silence": False,
        "script": "하나\n둘\n셋\n넷\n다섯",   # 대본 5줄 → 1.1초 간격 배치
    })
    job = _wait_status(server, data["job_id"], {"review_subtitle", "failed"}, timeout=180)
    assert job["status"] == "review_subtitle", job.get("errors")
    subs = job["subtitles"]
    assert len(subs) == 5

    res = _post(server, "/api/edit_render", {
        "job_id": data["job_id"], "subtitles": subs, "hook": "",
        "keep": None, "speed": 1, "quality": "draft",
        "trim_start_us": 1_000_000, "trim_end_us": 4_000_000,
    })
    assert res.get("ok")
    done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=240)
    assert done["status"] == "ok", done.get("errors")
    dur = ff.probe_duration_us(done["mp4"]) / 1e6
    assert 2.5 <= dur <= 3.6, dur  # 3초 구간만 사용
    assert "트림" in (done.get("note") or "")


def test_narration_fit_freeze_extends_video(server, tmp_path):
    """v0.42: 내레이션이 영상보다 길면 freeze로 영상을 늘려 전 문장을 담는다."""
    from cutdaejang.utils import ffmpeg as ff

    video = _make_talk_video(tmp_path / "nf.mp4")  # 5.5초
    data = _post(server, "/api/edit", {
        "video_path": video, "layout": "keep",
        "auto_subtitle": False, "cut_silence": False,
        "auto_edit": True, "auto_target_sec": 0, "quality": "draft",
        "narr_topic": "정리 습관 이야기", "narr_fit": "freeze",
    })
    job = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=300)
    assert job["status"] == "ok", job.get("errors")
    dur = ff.probe_duration_us(job["mp4"]) / 1e6
    assert dur > 6.5, dur  # 스텁 내레이션(~9초)이 5.5초 영상보다 길어 연장됨
    assert "연장" in (job.get("note") or "")


def test_narration_fit_drop_keeps_video_length(server, tmp_path):
    """v0.42: 예전 방식(drop)은 영상 길이를 유지 (뒷문장 생략)."""
    from cutdaejang.utils import ffmpeg as ff

    video = _make_talk_video(tmp_path / "nd.mp4")
    data = _post(server, "/api/edit", {
        "video_path": video, "layout": "keep",
        "auto_subtitle": False, "cut_silence": False,
        "auto_edit": True, "auto_target_sec": 0, "quality": "draft",
        "narr_topic": "정리 습관 이야기", "narr_fit": "drop",
    })
    job = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=300)
    assert job["status"] == "ok", job.get("errors")
    dur = ff.probe_duration_us(job["mp4"]) / 1e6
    assert dur <= 6.2, dur  # 원본 5.5초 유지 (여유 오차)


def test_generate_batch_two_topics(server):
    """v0.42 배치: 주제 2줄 → 영상 2개, 진행 표시·히스토리 기록."""
    res = _post(server, "/api/generate_batch", {
        "topics": ["배치 주제 하나", "배치 주제 둘"],
        "script_provider": "stub", "tts_provider": "stub",
    })
    assert res.get("count") == 2
    job = _wait_status(server, res["job_id"], {"ok", "partial", "failed"}, timeout=360)
    assert job["status"] == "ok", job.get("errors")
    assert len(job.get("mp4s") or []) == 2
    assert "배치 완성: 2/2" in (job.get("note") or "")
    # 개별 영상이 히스토리에 남아 재생 가능
    state = json.loads(_get(server, "/api/state").read())
    hist_titles = " ".join(r["title"] for r in state["history"])
    assert "배치 주제 하나" in hist_titles and "배치 주제 둘" in hist_titles


def test_generate_batch_rejects_empty(server):
    import urllib.error

    req = urllib.request.Request(
        server + "/api/generate_batch",
        data=json.dumps({"topics": ["  ", ""]}).encode(), method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_template_save_apply_delete(server):
    """v0.43 📋 템플릿 — 저장(허용 키만) → state 노출 → 삭제."""
    data = _post(server, "/api/template", {"name": "요리 쇼츠", "params": {
        "layout": "keep", "bgm": "따뜻한.mp3", "bgm_db": -9, "transition": "fade",
        "narr_fit": "loop", "quality": "ultra", "speed": 1.15,
        "video_path": "C:/개인폴더/영상.mp4",   # 작업별 입력 — 저장되면 안 됨
        "gemini_key": "AIza-비밀",              # 키 — 저장되면 안 됨
    }})
    assert data.get("ok") and "요리 쇼츠" in data["templates"]
    saved = data["templates"]["요리 쇼츠"]
    assert saved["transition"] == "fade" and saved["layout"] == "keep"
    assert "video_path" not in saved and "gemini_key" not in saved

    # state.settings.ui.templates 로 화면에 노출 (새로고침 후 목록 복원용)
    state = json.loads(_get(server, "/api/state").read())
    assert "요리 쇼츠" in ((state.get("settings") or {}).get("ui") or {}).get("templates", {})

    # 삭제 → 목록에서 사라짐 (deep_merge가 못 지우는 케이스 — save_settings_replace 검증)
    data2 = _post(server, "/api/template", {"op": "delete", "name": "요리 쇼츠"})
    assert data2.get("ok") and "요리 쇼츠" not in data2["templates"]
    state2 = json.loads(_get(server, "/api/state").read())
    assert "요리 쇼츠" not in ((state2.get("settings") or {}).get("ui") or {}).get("templates", {})

    # 이름 없으면 400
    try:
        _post(server, "/api/template", {"name": "  "})
        raise AssertionError("400이어야 함")
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_edit_photo_transition_fade_and_branding(server, tmp_path):
    """v0.43 — 사진 영상에 전환(fade) 적용 + 설정의 인트로가 완성본 앞에 붙는지."""
    from cutdaejang.utils import ffmpeg as ff

    imgs_dir = tmp_path / "photos"
    imgs_dir.mkdir()
    for i, c in enumerate(["white", "white"]):
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={c}:s=640x1136:d=0.1", "-frames:v", "1",
                str(imgs_dir / f"{i}.png")])
    intro = tmp_path / "intro.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=red:s=640x1136:d=0.1", "-frames:v", "1", str(intro)])
    _post(server, "/api/settings", {"settings": {"branding": {"intro": str(intro)}}})
    try:
        data = _post(server, "/api/edit", {
            "photo_path": str(imgs_dir), "photo_sec": 4, "transition": "fade",
            "auto_edit": True, "auto_target_sec": 0, "layout": "shorts",
            "stt_provider": "stub",
        })
        job = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=300)
        assert job["status"] in ("ok", "partial")
        out = job.get("mp4")
        assert out
        # 인트로(2.5초) + 본편(4초) — 브랜딩이 실제로 붙어 길이가 늘었는지 실측
        dur_s = ff.probe_duration_us(out) / 1e6
        assert 5.9 <= dur_s <= 7.2, f"인트로 포함 길이가 이상함: {dur_s:.2f}s"
        assert "인트로" in (job.get("note") or "") or "인트로" in (job.get("tts_warn") or "")
    finally:  # 다른 테스트가 브랜딩 영향을 받지 않게 원상복구
        _post(server, "/api/settings", {"settings": {"branding": {"intro": "", "outro": ""}}})
