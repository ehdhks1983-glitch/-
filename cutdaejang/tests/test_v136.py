"""v1.36 — 목록 72(AI 영상을 각 경로에) · 73(업로드 키트 BGM 크레딧).

회원님 32차:
> "AI영상만들기가 긴영상 가로랑 똑같은데 왜 굳이 저기에 넣어놓은 거야?
>  **각 템플릿 카테고리에 적용을 시키라고 한 거였지.** 이유가 뭐야?"

맞는 지적이었다. 31차의 «어디 포지션에 들어가 있냐»를 «못 찾겠다»로 읽고
바로가기 카드를 하나 더 만들었는데, 그건 같은 방(sectionCard)으로 가는
**두 번째 문**일 뿐이었다. 64·70번에서 «흩어져 헷갈린다»를 고쳐 놓고
새 중복을 만든 셈이다.

이번 판: ①그 문을 없애고 ②AI 영상 만들기 «안»에 진짜로 붙였다.

회원님 33차:
> "업로드 키트에서 유튜브 설명에 이 부분(BGM 크레딧) 들어가는 것도 빼줘"
"""

import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import background_generator as bg
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.47.2"


# ── 72 ①: 같은 방으로 가는 두 번째 문 ─────────────────────────
def test_the_duplicate_front_door_is_gone():
    """🔴 「✨ AI로 영상 만들기」는 「긴 영상」과 같은 화면을 열었다."""
    assert "aiclip" not in HTML, "죽은 흔적이 남아 있으면 다음 사람이 헷갈린다"
    assert HTML.count('class="modecard"') == 6
    titles = re.findall(r'<span class="mc-title">([^<]+)</span>', HTML)
    assert "AI로 영상 만들기" not in titles
    assert "긴 영상 (가로 16:9)" in titles, "진짜 문은 남아 있어야 한다"


def test_the_ai_hint_now_hangs_on_the_mode_not_the_door():
    """문을 없앴으니 안내는 «지금 모드»가 켜 줘야 한다 — 아니면 다시 안 보인다."""
    body = JS.split("function applySecMode(){")[1].split("\n}")[0]
    assert "$('secAiTip')" in body
    assert "classList.toggle('hidden', full)" in body


# ── 72 ②: 배경 조립이 «영상 칸»을 받는다 ──────────────────────
@pytest.mark.parametrize("path,want", [
    ("a.png", False), ("b.jpg", False), ("c.WEBP", False),
    ("d.mp4", True), ("e.MOV", True), ("f.webm", True), ("g.mkv", True),
])
def test_video_spans_are_recognised(path, want):
    assert bg._is_video_span(path) is want


def test_a_mixed_image_and_video_background_assembles(tmp_path):
    """🎬 이게 되면 «장면 하나만 움직이는 영상»이 성립한다 (목록 72 ②).

    짧은 클립(2초)이 긴 칸(4초)을 채우는지까지 본다 — AI 클립은 보통 5초라
    문장 길이와 안 맞는 게 정상이다.
    """
    from cutdaejang.spec import Canvas
    from cutdaejang.utils import ffmpeg as ff

    img = tmp_path / "a.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "gradients=size=1080x1920:duration=0.1:rate=1", "-frames:v", "1", str(img)])
    vid = tmp_path / "clip.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "testsrc=size=1280x720:duration=2:rate=30", "-pix_fmt", "yuv420p", str(vid)])
    out = bg.scene_slideshow([(str(img), 3_000_000), (str(vid), 4_000_000)],
                             str(tmp_path / "bg.mp4"), Canvas(w=1080, h=1920, fps=30))
    assert ff.probe_video_size(out) == (1080, 1920)
    dur = ff.probe_duration_us(out) / 1e6
    assert 6.7 < dur < 7.3, f"칸 길이(3+4초)를 지켜야 한다 — {dur}"


def test_a_moving_scene_does_not_get_ken_burns_on_top():
    """이미 움직이는 화면에 줌을 겹치면 어지럽다."""
    body = SRC.replace("webui", "")  # (파일 혼동 방지용 무해한 치환)
    src = open(bg.__file__, encoding="utf-8").read()
    seg = src.split("def scene_slideshow(")[1]
    assert "if is_vid:" in seg
    assert "zoompan" in seg, "그림 칸은 여전히 켄번즈"
    order = seg.index("if is_vid:") < seg.index('elif motion in ("zoom_in", "zoom_out")')
    assert order, "영상 칸이 켄번즈 분기보다 먼저 걸러져야 한다"
    assert "-stream_loop" in seg, "짧은 클립이 칸을 채워야 한다"
    assert body is not None


# ── 72 ②: 장면 검토 화면에서 부를 수 있는가 ──────────────────
def test_each_scene_can_become_an_ai_video():
    body = JS.split("function renderScenes(")[1].split("\nasync function ")[0]
    assert "sceneAiClip(e, s.i)" in body
    assert "✨ AI 영상으로" in body
    assert "sceneClipClear(e, s.i)" in body, "되돌릴 길이 있어야 한다"
    assert "🎬" in body, "영상인 장면은 그림과 구분돼 보여야 한다"


def test_the_cost_dialog_is_shared_not_duplicated():
    """요금 안내·확인 절차가 경로마다 갈라지면 한쪽이 새는 구멍이 된다."""
    assert JS.count("function _aiClipShow(") == 1
    for fn in ("function aiClipOpen(", "function sceneAiClip("):
        body = JS.split(fn)[1].split("\n}")[0]
        assert "_aiClipShow()" in body, fn


def test_the_scene_path_uses_the_videos_own_shape():
    """세로 영상인데 가로 클립을 만들면 화면 1/3만 채운다 (v1.25에서 배운 것)."""
    body = JS.split("function sceneAiClip(")[1].split("\n}")[0]
    assert "window._jobOrient === 'wide') ? '16:9' : '9:16'" in body
    go = JS.split("async function aiClipGo(")[1].split("\n}")[0]
    assert "window._aiClipAspect" in go


def test_the_section_path_still_fills_the_box():
    """장면 경로를 붙이면서 구간 경로가 망가지면 안 된다."""
    body = JS.split("function aiClipOpen(")[1].split("\n}")[0]
    assert "window._aiClipDone = null;" in body, "이전 장면 작업이 남으면 엉뚱한 곳에 넣는다"
    go = JS.split("async function aiClipGo(")[1]
    assert "vi.value = j.clip;" in go


def test_confirmed_scenes_prefer_the_clip_over_the_image():
    api = SRC.split('elif path == "/api/confirm_scenes":')[1].split("elif path ==")[0]
    assert 'clip = str(s.get("clip") or "")' in api
    assert "imgs[idx] = clip" in api


@pytest.mark.parametrize("api,what", [
    ("/api/scene_clip", "장면에 AI 영상 붙이기"),
    ("/api/scene_clip_clear", "그림으로 되돌리기"),
])
def test_the_scene_clip_apis_exist(api, what):
    assert f'elif path == "{api}":' in SRC, what


def test_scene_clip_refuses_a_still_image():
    """그림을 «영상 칸»에 넣으면 배경 조립이 엉뚱하게 돈다."""
    api = SRC.split('elif path == "/api/scene_clip":')[1].split("elif path ==")[0]
    assert "background_generator._is_video_span(src)" in api
    assert "영상 파일(mp4/mov/webm 등)만" in api


# ── 73: 업로드 키트 BGM 크레딧 ────────────────────────────────
def test_the_bgm_credit_is_out_of_the_youtube_description():
    assert 'kit["description"] = (kit.get("description", "").rstrip() + "\\n\\n" + credit)' not in SRC
    assert 'kit["bgm_credit"] = credit' in SRC
    assert "(설명란에 그대로 붙여넣기 — BGM 크레딧 포함)" not in HTML


def test_the_credit_is_still_available_separately():
    """CC BY는 «저작자 표시»가 사용 조건이라 지우면 안 된다 — 옮긴 것이다."""
    assert 'id="kitBgm"' in HTML and 'id="kitBgmRow"' in HTML
    assert "설명란 맨 아래에" in HTML
    body = JS.split("function renderKit(")[1]
    assert "kit.bgm_credit" in body
    assert "$('kitBgmRow').classList.toggle('hidden', !bc);" in body, "없으면 칸도 안 보여야"


def test_my_own_music_adds_nothing_at_all():
    """내 음원은 표시 «의무»가 없다 — 예전엔 파일 이름이 설명문에 들어갔다."""
    body = SRC.split("def _bgm_credit(")[1].split("\ndef ")[0]
    assert 'return f"🎵 BGM: {stem}"' not in body
    assert body.rstrip().endswith('return ""      # 🎵 v1.36: 내 음원이면 표시할 «의무»가 없다 — 잡음만 된다 (목록 73)')


def test_kit_text_puts_the_credit_in_its_own_block():
    body = SRC.split("def _kit_text(")[1].split("\ndef ")[0]
    assert 'kit.get("bgm_credit")' in body
    assert "🎵 음원 크레딧" in body


# ── 화면이 여전히 성한가 ──────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML


# ── 72 ③: 사진으로 만드는 경로(사진·블로그·쇼핑)에도 AI 영상 ──────
def test_all_three_photo_paths_can_insert_an_ai_video():
    """«각 템플릿 카테고리에» — 사진 경로 셋에 전부 붙었는지."""
    assert HTML.count("addAiClipPhoto(event,") == 3
    for where in ("'wl'", "'shop'", "'photo'"):
        assert f"addAiClipPhoto(event,{where})" in HTML, where


def test_the_photo_slideshow_accepts_a_video_slot(tmp_path):
    """🎬 사진 슬라이드쇼도 장면 배경과 «같은 규칙»이어야 코드가 안 갈라진다."""
    from cutdaejang.core.video_editor import photos_to_video
    from cutdaejang.utils import ffmpeg as ff

    img = tmp_path / "a.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "gradients=size=1280x720:duration=0.1:rate=1", "-frames:v", "1", str(img)])
    vid = tmp_path / "clip.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "testsrc=size=1280x720:duration=2:rate=30", "-pix_fmt", "yuv420p", str(vid)])
    out = photos_to_video([str(img), str(vid)], 8_000_000, str(tmp_path / "s.mp4"))
    assert ff.probe_video_size(out) == (1080, 1920)
    dur = ff.probe_duration_us(out) / 1e6
    assert 7.6 < dur < 8.4, f"전체 길이 약속(8초)을 지켜야 한다 — {dur}"


def test_photo_inputs_no_longer_reject_a_clip(tmp_path):
    """🔴 여기서 막혀 있었다 — 클립을 넣는 순간 «영상 만들기»가 통째로 실패했다."""
    from cutdaejang.core.video_editor import resolve_photo_inputs
    from cutdaejang.utils import ffmpeg as ff

    img = tmp_path / "a.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "gradients=size=64x64:duration=0.1:rate=1", "-frames:v", "1", str(img)])
    vid = tmp_path / "clip.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "testsrc=size=64x64:duration=1:rate=5", "-pix_fmt", "yuv420p", str(vid)])
    got = resolve_photo_inputs(f"{img};{vid}")
    assert len(got) == 2 and got[1].endswith(".mp4")


def test_a_folder_still_picks_photos_only(tmp_path):
    """폴더에는 원본 영상이 같이 있는 경우가 흔하다 — 끌려 들어오면 안 된다."""
    from cutdaejang.core.video_editor import resolve_photo_inputs
    from cutdaejang.utils import ffmpeg as ff

    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "gradients=size=64x64:duration=0.1:rate=1", "-frames:v", "1",
            str(tmp_path / "a.png")])
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "testsrc=size=64x64:duration=1:rate=5", "-pix_fmt", "yuv420p",
            str(tmp_path / "원본.mp4")])
    got = resolve_photo_inputs(str(tmp_path))
    assert [p.split("/")[-1] for p in got] == ["a.png"]


def test_junk_files_are_still_refused(tmp_path):
    from cutdaejang.core.video_editor import resolve_photo_inputs

    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_photo_inputs(str(tmp_path / "note.txt"))


def test_the_preparing_soon_caveat_is_gone():
    """세 화면에 «자동으로 끼워 넣는 기능은 준비 중»이라 적혀 있었다 — 이제 된다."""
    assert "준비 중이에요" not in HTML
    assert "[✨ AI 영상 넣기]" in HTML


def test_the_photo_paths_use_their_own_shape():
    body = JS.split("function addAiClipPhoto(")[1].split("\n}")[0]
    for sel in ("wlOrientSel", "shopOrientSel", "editLayout"):
        assert sel in body, sel
    assert "(orient === 'wide') ? '16:9' : '9:16'" in body
