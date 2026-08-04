"""v1.34 — 목록 63: 16:9를 골라도 세로로 나오고, 대본 길이가 45초로 박혀 있던 것.

회원님 27차 (스크린샷):
> "16 대 9로 만들어. 그러면 대본이 짧아서 짧은 영상뿐이 못 만드는 건가?
>  그리고 16대9로 제작 요청했는데 쇼츠로 영상이 나와"

둘 다 진짜 버그였다.

① 사진 슬라이드쇼를 만들 때 **화면 비율을 안 넘겼다.** 늘 세로(1080×1920)로 만든다.
   최종 프레임만 1920×1080이라 **가로 화면 한가운데 세로 그림 + 양옆 블러 띠**가 된다.
   블로그에서 긁어온 사진은 대개 가로(16:9)라 세로에 한 번, 가로에 또 한 번 우겨넣어
   그림이 조각만 남는다 — **이중 레터박스**.

② 블로그 대본 길이가 화면 코드에 `target_sec: 45`로 **박혀 있었다.**
   가로(롱폼)를 골라도 늘 45초짜리 대본이 나온다. 길이를 고를 칸조차 없었다.
"""

import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import edit_mode
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()


def test_version():
    assert __version__ == "1.37.0"


# ── ① 16:9인데 세로로 나오던 것 ────────────────────────────────
@pytest.mark.parametrize("layout,want", [
    ("shorts", (1080, 1920)),
    ("wide", (1920, 1080)),
    ("keep", (1080, 1920)),      # 모르는 값이면 기본(세로)
])
def test_canvas_for_layout(layout, want):
    assert edit_mode.canvas_for_layout(layout) == want


def test_the_slideshow_finally_asks_which_shape_to_make():
    """🔴 여기서 size를 안 넘겨 «가로 (16:9)»가 통째로 무시됐다."""
    body = SRC.split("if photo_path:")[1].split("\n        else:")[0]
    assert "size=edit_mode.canvas_for_layout(_lay)" in body
    assert '_lay = params.get("layout") or edit_cfg["layout"]' in body


@pytest.mark.parametrize("layout,want_w,want_h", [("shorts", 1080, 1920), ("wide", 1920, 1080)])
def test_a_landscape_photo_fills_a_landscape_frame(tmp_path, layout, want_w, want_h):
    """블로그 사진은 대개 가로다 — 가로를 골랐으면 화면을 꽉 채워야 한다."""
    from cutdaejang.core.video_editor import photos_to_video
    from cutdaejang.utils import ffmpeg as ff

    imgs = []
    for i in range(2):
        p = tmp_path / f"p{i}.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "gradients=size=1280x720:duration=0.1:rate=1",
                "-frames:v", "1", str(p)])
        imgs.append(str(p))
    out = photos_to_video(imgs, 4_000_000, str(tmp_path / f"s_{layout}.mp4"),
                          size=edit_mode.canvas_for_layout(layout))
    assert ff.probe_video_size(out) == (want_w, want_h)


# ── ② 대본이 늘 45초짜리이던 것 ────────────────────────────────
def test_the_hardcoded_45_seconds_is_gone():
    """🔴 «대본이 짧아서 짧은 영상뿐이 못 만드는 건가?» — 45초로 박혀 있었다."""
    # 블로그 카드는 «링크»와 «붙여넣기» 두 경로 모두 고른 길이를 써야 한다
    assert HTML.count("target_sec: wlTargetSec()") == 2
    # 블로그 카드 안에는 45초 박힌 값이 남아 있으면 안 된다
    wl = HTML.split("wlPasteText")[1].split("function startWeblink(")[0]
    assert "target_sec: 45" not in wl


def test_you_can_now_choose_the_length():
    assert 'id="wlLenSel"' in HTML
    for sec in ("45", "60", "90", "180", "300"):
        assert f'value="{sec}"' in HTML.split('id="wlLenSel"')[1].split("</select>")[0]


def test_choosing_landscape_bumps_the_default_length():
    """가로를 골랐는데 45초면 또 «짧은 영상밖에» 가 된다."""
    body = HTML.split("function onWlOrient(")[1].split("\nfunction ")[0]
    assert "'wide') ? '180' : '45'" in body
    assert "if(sel.dataset.touched) return;" in body, "직접 고른 값을 덮어쓰면 안 된다"
    assert 'onchange="onWlOrient()"' in HTML


def test_the_length_cap_no_longer_chops_long_scripts():
    """3~5분 대본이 180초에서 잘리면 뒷부분이 통째로 날아간다."""
    assert "photo_sec: Math.max(10, Math.min(180," not in HTML
    assert HTML.count("photo_sec: Math.max(10, Math.min(600,") == 2   # 블로그 + 쇼핑
    assert "photo_sec = max(3.0, min(600.0, photo_sec))" in SRC
    assert "photo_sec = max(3.0, min(180.0, photo_sec))" not in SRC


def test_the_estimate_works_before_the_script_exists():
    """대본을 받기 «전»에도 고른 길이로 예상 시간을 말해 준다."""
    body = HTML.split("function updateEta(")[1].split("\nfunction ")[0]
    assert "lines ? Math.max(10, Math.min(600," in body
    assert ": wlTargetSec()" in body


def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
