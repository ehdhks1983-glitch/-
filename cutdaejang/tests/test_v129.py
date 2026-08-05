"""v1.29 — 목록 58(«목소리만 다시»가 대본 영상을 거절) + 59(편집 폼 말 속도 무시).

회원님 24차 (스크린샷 + 말씀):
> "내가 스샷 찍은 건 사진 기반으로 만든 영상이 편집이 안 돼서 하는 소리야.
>  목소리면 영상은 그대로 하고 목소리만 변경되게끔 해야 하는 거 아니야?"

맞다. 그래서 이 판은 **이미 만든 화면을 그대로 두고 목소리만** 새로 읽힌다.

🔴 v1.27에서 내가 만든 것 두 가지가 여기서 드러났다.
  ① 「목소리만 다시」 관문이 «script.json 파일이 있나»만 봤다. 블로그·쇼핑·구간·사진
     카드는 편집 경로로 가고 그쪽은 그 파일을 안 쓴다 → 대본으로 만든 영상인데도
     "대본으로 만든 영상에서만 가능해요"로 퇴짜.
  ② 편집·구간 폼에 «말 속도» 칸을 만들어 놓고 뒤에서 안 읽었다. 바꿔도 아무 일이
     안 일어났다. v1.27 시험은 «폼이 값을 보내는지»만 봤지 «뒤에서 쓰는지»는
     안 봤다 — 그래서 못 잡았다. 이번엔 그걸 본다.
"""

import ast
import re
from pathlib import Path

import pytest

from cutdaejang import __version__, config
from cutdaejang.gui import webui

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
HTML = webui._apply_links(webui._HTML)


def test_version():
    assert __version__ == "1.42.0"


# ── 목록 59: 말 속도가 «뒤에서» 실제로 쓰이나 ───────────────────
def test_speed_settings_clamps_and_ignores_junk():
    base = config.deep_merge(config.DEFAULTS, {})
    assert webui._speed_settings(base, "1.12")["audio"]["speech_speed"] == pytest.approx(1.12)
    assert webui._speed_settings(base, "9")["audio"]["speech_speed"] == 2.0
    assert webui._speed_settings(base, "0.1")["audio"]["speech_speed"] == 0.5
    for junk in ("", None, "말도안됨"):
        assert webui._speed_settings(base, junk)["audio"]["speech_speed"] == 1.0


def test_every_edit_stage_actually_applies_the_chosen_speed():
    """🔴 v1.27 시험이 놓친 자리 — 폼이 보내는 것과 뒤에서 쓰는 건 다른 문제다.

    편집 경로에서 설정을 읽는 자리가 **하나라도** 그냥 `config.load_settings()`면,
    회원님이 고른 말 속도는 그 단계에서 조용히 버려진다.
    """
    tree = ast.parse(SRC)
    funcs = []

    def walk(node):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append((n.name, n.lineno, n.end_lineno))
            walk(n)

    walk(tree)

    def owner(line):
        best = None
        for nm, a, b in funcs:
            if a <= line <= b and (best is None or a > best[1]):
                best = (nm, a, b)
        return best[0] if best else ""

    EDIT_STAGES = {"_run_edit", "_do_edit_render", "_do_edit_split"}
    seen = set()
    for i, ln in enumerate(SRC.splitlines(), 1):
        if "config.load_settings()" not in ln:
            continue
        fn = owner(i)
        if fn in EDIT_STAGES:
            seen.add(fn)
            assert "_speed_settings(" in ln, (
                f"{fn} {i}행: 말 속도를 안 거치고 설정을 읽는다 — 고른 속도가 버려진다")
    assert seen == EDIT_STAGES, f"확인 못 한 단계: {EDIT_STAGES - seen}"


def test_speed_survives_into_the_second_stage():
    """1단계(분석)와 2단계(렌더)는 따로 도는 함수다 — edit_params로 넘겨야 산다."""
    assert '"narr_speed": str(params.get("narr_speed") or "")' in SRC
    assert "def _job_narr_speed(" in SRC


# ── 목록 58: 편집 경로 영상도 «목소리만 다시» ──────────────────
BLOG = {   # 블로그 카드가 실제로 보내는 모양
    "photo_path": "", "photo_sec": 40, "layout": "shorts", "quality": "ultra",
    "script": "첫 문장\n둘째 문장", "script_tts": True, "narr_voice": "Kore",
    "auto_subtitle": False, "cut_silence": False, "bgm": "무료.mp3",
    "sub_style": "네온", "narr_topic": "", "auto_multi": True,
}
JOB = {"edit_params": {"narration": True, "narr_file": "", "narr_voice": "Kore"},
       "subtitles": [{"text": "첫 문장(내가 고침)"}, {"text": "둘째 문장"}]}


@pytest.fixture
def made(tmp_path):
    """이미 만들어 둔 사진 영상 한 벌."""
    photos = []
    for i in range(3):
        p = tmp_path / f"p{i}.jpg"
        p.write_bytes(b"x")
        photos.append(str(p))
    (tmp_path / "slideshow.mp4").write_bytes(b"x")
    old = dict(BLOG, photo_path=";".join(photos))
    job = dict(JOB, cut_video=str(tmp_path / "slideshow.mp4"))
    return job, old, tmp_path


def test_voice_retouch_keeps_the_picture_and_only_swaps_the_voice(made):
    """회원님 요구 그대로 — 화면·자막 글·꾸미기는 그대로, 목소리만 바뀐다."""
    job, old, d = made
    p, why = webui._edit_voice_params(job, old, {"voice": "Puck", "narr_speed": "1.12"}, d)
    assert not why
    assert p["narr_voice"] == "Puck" and p["narr_speed"] == "1.12"
    # 사진은 그대로 재사용 — AI 그림으로 바꿔치기하면 완전히 다른 영상이 된다
    assert p["photo_path"] == old["photo_path"]
    assert p["quality"] == "ultra" and p["sub_style"] == "네온" and p["bgm"] == "무료.mp3"
    # 대본은 **완성된 자막 글**을 그대로 — AI에게 다시 쓰게 하면 말 자체가 바뀐다
    assert p["script"] == "첫 문장(내가 고침)\n둘째 문장"
    assert p["script_tts"] is True
    assert p["auto_edit"] is True          # 고칠 게 없으니 자막 검토는 건너뛴다
    assert p["auto_subtitle"] is False and p["cut_silence"] is False
    for k in ("narr_topic", "narr_analyze", "auto_multi"):
        assert k not in p, f"{k}가 남으면 대본·구성이 통째로 다시 만들어진다"


def test_elevenlabs_voice_gets_the_prefix_the_edit_path_expects(made):
    """편집 경로는 narr_voice 한 칸에 제공자까지 담는다 — el: 없으면 성우로 못 읽는다."""
    job, old, d = made
    p, _ = webui._edit_voice_params(
        job, old, {"voice": "abc123", "tts_provider": "elevenlabs"}, d)
    assert p["narr_voice"] == "el:abc123"


def test_falls_back_to_the_video_when_the_photos_are_gone(made):
    job, old, d = made
    p, why = webui._edit_voice_params(
        job, dict(old, photo_path=str(d / "없는사진.jpg")), {"voice": "Puck"}, d)
    assert not why
    assert p["photo_path"] == "" and Path(p["video_path"]).name == "slideshow.mp4"


def test_uses_the_original_script_when_there_was_no_review(made):
    _job, old, d = made
    bare = {"edit_params": {"narration": True}}
    p, why = webui._edit_voice_params(bare, old, {"voice": "Puck"}, d)
    assert not why and p["script"] == "첫 문장\n둘째 문장"


@pytest.mark.parametrize("job,mark", [
    ({"edit_params": {"narration": True, "narr_file": "내목소리.wav"}}, "직접 녹음"),
    ({"edit_params": {"narration": False}}, "원본 소리"),
    ({"edit_params": {"narration": True}}, "대본이 남아 있지 않아"),
])
def test_says_why_when_it_really_cannot(job, mark, tmp_path):
    old = {} if "대본" in mark else dict(BLOG)
    p, why = webui._edit_voice_params(job, old, {"voice": "Puck"}, tmp_path)
    assert p is None and mark in why


def test_no_source_left_is_a_clear_message(tmp_path):
    """사진도 영상도 없으면 «지원 안 함»이 아니라 «지워졌다»고 말해야 한다."""
    p, why = webui._edit_voice_params(
        JOB, dict(BLOG, photo_path="/없음/a.jpg"), {"voice": "Puck"}, tmp_path)
    assert p is None and "지워져" in why


def test_retouch_no_longer_refuses_script_made_edit_videos():
    """🔴 회원님이 보신 그 문구가 편집 경로에서 나오면 안 된다."""
    body = SRC.split("def _retouch(")[1].split("\n    def ")[0]
    assert "_edit_voice_params(job, old_params, params, job_dir)" in body
    # v1.30부터 «빠른 길 먼저» 재실행으로 바뀌었다 (목록 60)
    assert "_queue_job(new_id, _run_revoice, new_id, src_id, new_params, workdir)" in body
    # 옛 문구는 통째로 사라져야 한다 (편집 경로 영상엔 거짓말이었다)
    assert "대본으로 만든 영상(AI 영상 만들기)에서만 가능해요" not in SRC


def test_edit_jobs_now_remember_their_settings():
    """껐다 켜면 부분 수정이 안 되던 것 — 편집 작업도 입력값을 히스토리에 남긴다."""
    body = SRC.split("def _do_edit_render(")[1].split("\n    finally:")[0]
    rec = body.split("_record_simple_history(")[1][:600]
    assert 'params=(_get_job(job_id) or {}).get("params")' in rec


# ── 버튼을 보여주고 나서 거절하지 않는다 ────────────────────────
def test_button_is_hidden_when_the_video_cannot_do_it():
    assert "function voiceRetouchWhyNot(" in HTML
    assert 'id="rtVoiceBox"' in HTML and 'id="rtVoiceNo"' in HTML
    body = HTML.split("function toggleRetouch(")[1].split("\nfunction ")[0]
    assert "voiceRetouchWhyNot(window._curJob)" in body
    assert "rtVoiceBox" in body and "rtVoiceNo" in body
    assert "window._curJob = job || null;" in HTML   # poll이 채워 준다


def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
