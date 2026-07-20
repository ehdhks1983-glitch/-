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
    # v0.47: 제목 옆 태그 + 플랫폼별 섹션
    assert 2 <= len(kit["title_tags"]) <= 3
    assert kit["tiktok"]["caption"] and 3 <= len(kit["tiktok"]["hashtags"]) <= 5
    assert kit["instagram"]["caption"] and kit["naver_clip"]["title"]
    assert len(kit["naver_clip"]["tags"]) >= 8 and kit["threads"]["post"]
    assert kit["threads"]["topic"]  # 스레드는 토픽 태그 1개
    # 파일 저장 확인 (플랫폼 섹션 포함)
    assert kit_res["path"].endswith("업로드킷.txt")
    saved = Path(kit_res["path"]).read_text(encoding="utf-8")
    assert "제목 후보" in saved and "태그" in saved and "카테고리" in saved
    for sec in ("【틱톡】", "【인스타그램 릴스】", "【네이버 클립】", "【스레드】"):
        assert sec in saved, sec
    assert "#" in saved.split("1. ")[1].splitlines()[0]  # 제목 옆 태그가 붙어 저장


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
    # v0.40: 어떤 배경이 쓰였는지 완료 화면에 표시
    # (v0.45부터 AI 배경 기본 켬 — 키 없는 환경이라 사유는 "Gemini 키 없음")
    assert "기본 그라데이션" in job.get("bg_source", "") and "키 없음" in job["bg_source"]
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
    # v0.44.1: 화면에 바로 보여줄 내용도 응답에 포함 (파일과 동일)
    assert data.get("text") == text


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


def test_generate_remembers_bg_style(server):
    """v0.45 — 생성 폼에서 고른 장면 그림체가 설정(bg.image_style)에 기억되는지."""
    from cutdaejang import config

    data = _post(server, "/api/generate", {
        "topic": "그림체 기억 테스트", "auto": True,
        "script_provider": "stub", "tts_provider": "stub", "bg_style": "수채화",
    })
    _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=240)
    assert config.load_settings()["bg"]["image_style"] == "수채화"
    # 키 없는 환경 → 장면 이미지 없이 기본 그라데이션으로 정상 완성
    state = json.loads(_get(server, "/api/state").read())
    job = next(j for j in state["jobs"] if j["id"] == data["job_id"])
    assert job["status"] == "ok"
    assert "그라데이션" in (job.get("bg_source") or "")


def test_eleven_voices_endpoint_no_key(server):
    """v0.46 — 키 없으면 빈 목록 + no_key (UI는 라디오 자체를 숨김)."""
    data = _post(server, "/api/eleven_voices", {})
    assert data.get("voices") == [] and data.get("no_key") is True


def test_eleven_voices_listing_and_cache(monkeypatch):
    """v0.46 — /v1/voices 응답 파싱 (클론 먼저·이름순) 몽키패치 검증."""
    import io
    import urllib.request as ur

    from cutdaejang.core import tts_engine as te

    payload = json.dumps({"voices": [
        {"voice_id": "v2", "name": "Bella", "category": "premade"},
        {"voice_id": "v3", "name": "Adam", "category": "premade"},
        {"voice_id": "v1", "name": "내클론", "category": "cloned"},
        {"name": "id없음"},
    ]}).encode()

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(ur, "urlopen", lambda req, timeout=30: FakeResp(payload))
    voices = te.list_elevenlabs_voices()
    assert [v["voice_id"] for v in voices] == ["v1", "v3", "v2"]  # 클론 먼저, 이름순
    assert voices[0]["category"] == "cloned"


def test_upload_kit_on_generated_job(server):
    """v0.47 회귀 — 완전 자동 '생성' 영상의 키트: script.json 대본(dict 문장)을 읽다
    서버가 죽던 잠복 버그. 이제 정상 생성 + 플랫폼 섹션 포함."""
    res = _post(server, "/api/generate", {
        "topic": "생성 키트 회귀", "auto": True,
        "script_provider": "stub", "tts_provider": "stub",
    })
    job = _wait_status(server, res["job_id"], {"ok", "partial", "failed"}, timeout=240)
    assert job["status"] == "ok", job.get("errors")
    k = _post(server, "/api/upload_kit", {"job_id": res["job_id"]})
    assert k["kit"]["titles"] and k["kit"]["tiktok"]["caption"]
    assert k["kit"]["threads"]["post"]


def test_thumbnail_api_preset(server, tmp_path):
    """v0.48 — 썸네일 프리셋 API: 임팩트 스타일이 UI 선택값으로 만들어지는지."""
    from cutdaejang.utils import ffmpeg as ff

    bg = tmp_path / "tb.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=0x224466:s=1280x720:d=0.1", "-frames:v", "1", str(bg)])
    data = _post(server, "/api/thumbnail", {
        "title": "프리셋 테스트 | 테스트", "bg_path": str(bg), "preset": "임팩트"})
    assert data.get("ok") and data["path"].endswith("thumbnail.png")
    assert ff.probe_video_size(data["path"]) == (1280, 720)
    html = _get(server, "/").read().decode("utf-8")
    assert 'id="thumbStyleSel"' in html and 'id="thumbAiBg"' in html


def test_edit_render_custom_margin_v(server, tmp_path):
    """v0.49 — 검토 화면에서 드래그한 자막 위치(margin_v)가 렌더에 실제 반영되는지.

    자막을 화면 위쪽(margin_v 1200)으로 올리면, 기본(480)이라면 검정이었을
    상단 영역에 자막 픽셀(흰 글자/외곽선)이 나타난다 — 픽셀로 실측.
    """
    import subprocess

    from cutdaejang.utils import ffmpeg as ff

    def render_with(margin_v, name):
        video = _make_talk_video(tmp_path / f"{name}.mp4")
        data = _post(server, "/api/edit", {
            "video_path": video, "layout": "shorts",
            "auto_subtitle": False, "cut_silence": False, "quality": "draft",
            "script": "가나다라마바사 아자차카타파하",
        })
        job = _wait_status(server, data["job_id"], {"review_subtitle", "failed"})
        assert job["status"] == "review_subtitle"
        body = {"job_id": data["job_id"], "subtitles": job["subtitles"], "hook": ""}
        if margin_v:
            body["margin_v"] = margin_v
        _post(server, "/api/edit_render", body)
        done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=240)
        assert done["status"] == "ok", done.get("errors")
        return done["mp4"]

    def bright_ratio_at(mp4, y_frac):
        # 특정 높이 가로줄에서 아주 밝은(흰 글자) 픽셀 비율 — 평균 스케일은
        # 글자를 희석시키므로 원본 해상도에서 임계값으로 센다
        raw = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-ss", "1.0", "-i", mp4, "-frames:v", "1",
             "-vf", f"crop=1080:80:0:{int(1920 * y_frac)}",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True).stdout
        return sum(1 for b in raw if b > 220) / max(len(raw), 1)

    high = render_with(1200, "mv_high")   # 화면 중간보다 위로 올림
    # margin_v=1200 → 자막 하단이 y≈720(=1920-1200) 부근 → 그 위 줄에 글자 존재
    assert bright_ratio_at(high, 0.33) > 0.05, "올린 위치에 자막이 없음"

    low = render_with(0, "mv_low")        # 기본(480) — 같은 높이엔 자막이 없어야
    assert bright_ratio_at(low, 0.33) < 0.02, "기본 위치인데 상단에 자막이 있음"


def test_scene_review_flow(server, monkeypatch):
    """v0.50 — 장면 검토: 확정 → 그림 준비 → review_scenes → 한 장 재생성 → 확정 → 완성.

    가짜 이미지 제공자로 전체 왕복을 검증: 검토 확정 후 렌더에서 장면을
    다시 만들지 않고(생성 호출 수 고정) 확정본 그대로 쓰는지까지.
    """
    from cutdaejang.gui import webui
    from cutdaejang.utils import ffmpeg as ff

    calls = []  # (prompt, ref_png)

    class FakeImg:
        def generate(self, prompt, out_path, canvas, ref_png=None):
            calls.append((prompt, ref_png))
            ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c=orange:s={canvas.w}x{canvas.h}:d=0.1",
                    "-frames:v", "1", str(out_path)])
            return str(out_path)

    fake = FakeImg()
    monkeypatch.setattr(webui, "_ai_image_setup", lambda params, settings: (fake, ""))
    _post(server, "/api/settings", {"settings": {"bg": {"character": "해골"}}})
    try:
        res = _post(server, "/api/generate", {
            "topic": "장면 검토 흐름", "auto": False,
            "script_provider": "stub", "tts_provider": "stub",
        })
        _wait_status(server, res["job_id"], {"awaiting_review"})
        _post(server, "/api/confirm", {
            "job_id": res["job_id"], "title": "장면 검토 제목",
            "sentences": ["첫 장면 문장입니다.", "둘째 장면 문장입니다.", "셋째 장면 문장입니다."],
        })
        job = _wait_status(server, res["job_id"], {"review_scenes", "ok", "failed"})
        assert job["status"] == "review_scenes", job.get("errors")
        scenes = job["scenes"]
        assert len(scenes) == 3 and all(s["ok"] for s in scenes)
        assert scenes[0]["prompt"] and scenes[0]["text"].startswith("첫")
        # 캐릭터 설정 → 2번째 장면부터 첫 성공작을 참조로 전달 (일관성)
        assert calls[0][1] is None and calls[1][1] and calls[2][1]
        # 검토 이미지가 브라우저로 서빙되는지
        png = _get(server, f"/scene/{res['job_id']}/0").read()
        assert png[:4] == b"\x89PNG"

        # 한 장면만 프롬프트 고쳐 다시 그리기 — 다른 성공작을 참조로 사용
        regen = _post(server, "/api/scene_regen", {
            "job_id": res["job_id"], "index": 1, "prompt": "파도가 몰아치는 밤바다"})
        assert regen.get("ok")
        assert "파도가 몰아치는" in calls[3][0] and calls[3][1]
        state = json.loads(_get(server, "/api/state").read())
        j = next(x for x in state["jobs"] if x["id"] == res["job_id"])
        assert j["scenes"][1]["prompt"] == "파도가 몰아치는 밤바다"

        # 확정 → 렌더 (장면 재생성 없이 확정본 사용)
        n_before = len(calls)
        assert _post(server, "/api/confirm_scenes", {"job_id": res["job_id"]}).get("ok")
        done = _wait_status(server, res["job_id"], {"ok", "partial", "failed"}, timeout=300)
        assert done["status"] == "ok", done.get("errors")
        assert done["title"] == "장면 검토 제목"
        assert "AI 장면 이미지 3/3장" in (done.get("bg_source") or "")
        # 렌더 중 추가 생성은 기본 배경 1장뿐 — 장면 3장을 다시 만들지 않음
        assert len(calls) == n_before + 1
    finally:
        _post(server, "/api/settings", {"settings": {"bg": {"character": ""}}})


def test_fetch_bgm_endpoint_and_ui(server, monkeypatch, tmp_path):
    """v0.50.1 — 화면 [⬇ 무료 BGM 받기]: 다운로드 스레드 → 상태 폴링 → 목록 반영."""
    from cutdaejang.core import orchestrator
    from cutdaejang.tools import fetch_bgm as fb

    html = _get(server, "/").read().decode("utf-8")
    assert 'id="bgmFetchBtn"' in html and "/api/fetch_bgm" in html
    assert 'id="aiBgOffWarn"' in html and "enableAiBg" in html  # AI 배경 꺼짐 경고

    def fake_fetch(url, dest):
        assert url.startswith("https://incompetech.com/")
        dest.write_bytes(b"ID3" + b"\x00" * 120_000)  # 100KB 이상이어야 성공 판정
        return True

    monkeypatch.setattr(fb, "fetch", fake_fetch)
    monkeypatch.setattr(orchestrator, "DEFAULT_BGM_DIR", tmp_path / "bgm")
    assert _post(server, "/api/fetch_bgm", {}).get("ok")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        st = json.loads(_get(server, "/api/state").read())
        if not st["bgm_fetch"]["running"]:
            break
        time.sleep(0.3)
    assert "14곡 준비 완료" in st["bgm_fetch"]["msg"], st["bgm_fetch"]
    assert len(st["bgm_files"]) == 14  # 새 폴더 목록이 state에 반영
    assert (tmp_path / "bgm" / fb.CREDIT_FILE).exists()  # 크레딧 파일 생성


def test_scene_manual_mode_flow(server, tmp_path):
    """v0.51 — ✍ 내가 넣기: 키 없이 검토 진입(비용 0) → 폴더/파일로 그림 삽입 → 완성.

    프롬프트만 뽑아 챗지피티/제미나이에서 직접 만들어 넣는 흐름의 서버 왕복.
    """
    from cutdaejang.utils import ffmpeg as ff

    _post(server, "/api/settings", {"settings": {"bg": {"scene_mode": "manual"}}})
    try:
        res = _post(server, "/api/generate", {
            "topic": "수동 그림 흐름", "auto": False,
            "script_provider": "stub", "tts_provider": "stub",
        })
        _wait_status(server, res["job_id"], {"awaiting_review"})
        _post(server, "/api/confirm", {
            "job_id": res["job_id"], "title": "수동 그림 제목",
            "sentences": ["첫 문장입니다.", "둘째 문장입니다.", "셋째 문장입니다."],
        })
        job = _wait_status(server, res["job_id"], {"review_scenes", "ok", "failed"})
        assert job["status"] == "review_scenes", job.get("errors")
        scenes = job["scenes"]
        assert len(scenes) == 3
        assert all(not s["ok"] and s["prompt"] for s in scenes)  # 그림 없음 + 프롬프트 존재

        # 내가 만든 그림 폴더 (이름순 2장) → 1·2번 장면에
        folder = tmp_path / "my_imgs"
        folder.mkdir()
        for k, c in enumerate(["red", "lime"]):
            ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c={c}:s=600x900:d=0.1", "-frames:v", "1",
                    str(folder / f"{k + 1:02d}.png")])
        r = _post(server, "/api/scene_folder", {"job_id": res["job_id"],
                                                "folder": str(folder)})
        assert r["applied"] == 2 and r["total"] == 3

        # 3번 장면은 파일 1장으로 직접 (임의 비율 → 캔버스 정규화 확인)
        one = tmp_path / "solo.jpg"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "color=c=blue:s=800x500:d=0.1", "-frames:v", "1", str(one)])
        last_i = scenes[2]["i"]
        assert _post(server, "/api/scene_upload", {
            "job_id": res["job_id"], "index": last_i, "path": str(one)}).get("ok")
        png = _get(server, f"/scene/{res['job_id']}/{last_i}").read()
        assert png[:4] == b"\x89PNG"
        state = json.loads(_get(server, "/api/state").read())
        j = next(x for x in state["jobs"] if x["id"] == res["job_id"])
        assert all(s["ok"] for s in j["scenes"])  # 3장 모두 채워짐

        assert _post(server, "/api/confirm_scenes", {"job_id": res["job_id"]}).get("ok")
        done = _wait_status(server, res["job_id"], {"ok", "partial", "failed"}, timeout=300)
        assert done["status"] == "ok", done.get("errors")
        assert "AI 장면 이미지 3/3장" in (done.get("bg_source") or "")
    finally:
        _post(server, "/api/settings", {"settings": {"bg": {"scene_mode": "auto"}}})


def test_hook_ui_order_style_and_voice_pickers(server):
    """v0.52 — ① AI 제목 추천이 입력칸 위로(순서 교체, 양 폼) ② 글씨 스타일 선택
    ③ 생성 폼에도 색 칩 ④ 내 목소리 등록에 📁 파일 선택 + 단계 안내 링크."""
    html = _get(server, "/").read().decode("utf-8")
    # 순서: 편집 폼 — 추천 입력(editHookTopic)·후보(editHookCands)가 제목 입력(editHook)보다 위
    assert html.index('id="editHookTopic"') < html.index('id="editHookCands"') \
        < html.index('id="editHook"')
    # 순서: 생성 폼 — 추천 버튼·후보(genHookCands)가 제목 입력(genHook)보다 위
    assert html.index('id="genHookCands"') < html.index('id="genHook"')
    # 글씨 스타일 셀렉트 (양 폼) + 프리셋 4종
    assert 'id="hookStyleSel"' in html and 'id="genHookStyleSel"' in html
    for name in ("예능 노랑", "화이트 박스"):
        assert html.count(f'value="{name}"') == 2, name
    assert html.count('value="네온"') == 3  # 제목 프리셋 2곳 + 그림체(v0.45) 1곳
    # 생성 폼 색 칩 + 미리보기
    assert 'id="genHookColorChips"' in html and 'id="genHookPreview"' in html
    # 내 목소리 등록: 📁 픽커 2곳 + 단계 안내 링크
    assert "pickInto(event,'sovitsRef','audio')" in html
    assert "pickInto(event,'cloneFile','audio')" in html
    assert "elevenlabs.io/app/settings/api-keys" in html
    assert "처음이라면 이 순서대로" in html


def test_generate_remembers_hook_style(server):
    """v0.52 — 생성 폼에서 고른 제목 글씨 스타일이 설정(subtitle.hook_style)에 기억."""
    from cutdaejang import config

    data = _post(server, "/api/generate", {
        "topic": "제목 스타일 기억", "auto": True,
        "script_provider": "stub", "tts_provider": "stub", "hook_style": "예능 노랑",
    })
    job = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=240)
    assert job["status"] == "ok", job.get("errors")
    assert config.load_settings()["subtitle"]["hook_style"] == "예능 노랑"
    try:
        # 렌더된 spec에도 프리셋이 박혀 있는지 (제목 노랑 = &H0000D4FF는 ass에서 검증됨)
        state = json.loads(_get(server, "/api/state").read())
        j = next(x for x in state["jobs"] if x["id"] == data["job_id"])
        assert j["status"] == "ok"
    finally:
        _post(server, "/api/settings", {"settings": {"subtitle": {"hook_style": "기본"}}})


def test_pick_file_kind_routing(server, monkeypatch):
    """v0.51 — /api/pick_file kind: folder/image는 pick_path로, 기본은 기존 함수로."""
    from cutdaejang.gui import webui

    seen = []
    monkeypatch.setattr(webui, "pick_path", lambda kind, timeout=600.0: (
        seen.append(kind) or f"C:/선택/{kind}"))
    data = _post(server, "/api/pick_file", {"kind": "folder"})
    assert data["path"] == "C:/선택/folder" and seen == ["folder"]


def test_thumbnail_api_position(server, tmp_path):
    """v0.49 — 썸네일 글자 위치(pos_x/pos_y)가 실제로 반영되는지 픽셀 실측."""
    import subprocess
    from pathlib import Path

    from cutdaejang.utils import ffmpeg as ff

    bg = tmp_path / "pb.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=0x101820:s=1280x720:d=0.1", "-frames:v", "1", str(bg)])

    def yellow_in_band(png, y0, h):
        raw = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-i", str(png),
             "-vf", f"crop=1000:{h}:140:{y0},scale=40:10", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        px = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
        return any(r > 190 and g > 160 and b < 140 for r, g, b in px)

    d1 = _post(server, "/api/thumbnail", {
        "title": "위치 테스트", "bg_path": str(bg), "preset": "임팩트",
        "pos_x": 0.5, "pos_y": 0.2})
    assert d1.get("ok")
    top = str(tmp_path / "top.png")
    Path(d1["path"]).replace(top)
    assert yellow_in_band(top, 60, 220) and not yellow_in_band(top, 480, 220)

    d2 = _post(server, "/api/thumbnail", {
        "title": "위치 테스트", "bg_path": str(bg), "preset": "임팩트",
        "pos_x": 0.5, "pos_y": 0.78})
    assert d2.get("ok")
    assert yellow_in_band(d2["path"], 480, 220) and not yellow_in_band(d2["path"], 60, 220)
