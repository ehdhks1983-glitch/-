"""v1.28 — 목록 54: 영상에 박힌 자막 지우고 한국어 자막 넣기.

회원님 22차:
> "중국 영상으로 쿠팡파트너스를 많이 하거든? 그래서 자막을 지우고 영상을 제작하는데
>  이 기능이 있으면 좋을 것 같고 … 자막 지우는 기능은 타업체들도 엄청 많아.
>  필요 없는 자막이 있는 경우도 많아서"

찾는 방법을 고르기까지 실패가 한 번 있었다 — «밝은 화소 개수»로 찾으려니 배경이 밝으면
자막이 묻혀 아예 못 찾았다. 실제로 통한 건 **«흰 글자 + 검은 테두리» 때문에 한 줄 안에서
밝기가 급변하는 정도**다 (실측: 자막 줄 383점 vs 나머지 중앙값 1점).
"""

import re
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang.core import desub
from cutdaejang.gui import webui
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
HTML = webui._apply_links(webui._HTML)
W, H, SEC = 720, 1280, 6.0
SUB_Y = H - 190          # 자막을 그려 넣을 위치


def test_version():
    assert __version__ == "1.29.0"


@pytest.fixture(scope="module")
def subbed_video(tmp_path_factory):
    """아래쪽에 «중국어 자막»이 박힌 영상 — 회원님이 쓰시는 소재를 흉내."""
    tmp = tmp_path_factory.mktemp("desub")
    fonts = sorted((ROOT / "cutdaejang/resources/fonts").glob("*.ttf"))
    font = f"fontfile='{fonts[0]}':" if fonts else ""
    draws = [
        f"drawtext={font}text='这个产品真的很好用{i}':fontsize=44:fontcolor=white:"
        f"borderw=3:bordercolor=black:x=(w-tw)/2:y={SUB_Y}"
        f":enable='between(t,{i*2},{i*2+2})'" for i in range(3)]
    out = tmp / "cn.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", f"gradients=size={W}x{H}:duration={SEC}:rate=30:speed=0.02",
            "-vf", ",".join(draws), "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(out)])
    return out


@pytest.fixture(scope="module")
def plain_video(tmp_path_factory):
    """자막이 전혀 없는 영상 — 헛디텍션이 나면 안 된다."""
    tmp = tmp_path_factory.mktemp("plain")
    out = tmp / "plain.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", f"gradients=size={W}x{H}:duration=3:rate=30:speed=0.02",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)])
    return out


# ── 자막 위치 찾기 ─────────────────────────────────────────────
@requires_ffmpeg
def test_finds_the_burned_in_subtitle_band(subbed_video):
    band = desub.find_subtitle_band(str(subbed_video))
    assert band, "박힌 자막을 못 찾음"
    y0, y1 = band
    # 실제 자막은 SUB_Y부터 글자 높이(약 55px)만큼 — 여유 8px 포함해 겹치면 성공
    assert y0 <= SUB_Y + 10, f"너무 아래에서 찾음: {band}"
    assert y1 >= SUB_Y, f"너무 위에서 끝남: {band}"
    assert 10 < (y1 - y0) < H * 0.35, f"범위가 이상함: {band}"


@requires_ffmpeg
def test_no_false_alarm_on_a_video_without_subtitles(plain_video):
    """자막이 없는 영상을 «찾았다»고 하면 멀쩡한 화면을 지워 버린다."""
    assert desub.find_subtitle_band(str(plain_video)) is None


@requires_ffmpeg
def test_resolve_band_explains_itself_in_korean(subbed_video, plain_video):
    band, note = desub.resolve_band(str(subbed_video), "auto")
    assert band and "찾아 지웠어요" in note

    none_band, note2 = desub.resolve_band(str(plain_video), "auto")
    assert none_band is None
    assert "못 찾았어요" in note2 and "직접 지정" in note2   # 다음에 뭘 할지 알려준다

    man, note3 = desub.resolve_band(str(subbed_video), "manual", (900, 1000))
    assert man == (900, 1000) and "직접 지정" in note3

    bad, note4 = desub.resolve_band(str(subbed_video), "manual", (900, 800))
    assert bad is None and "거꾸로" in note4


# ── delogo 필터 만들기 ─────────────────────────────────────────
def test_delogo_never_touches_the_frame_edge():
    """🔴 실제로 한 번 터진 자리 — delogo는 가리는 칸 **바깥** 화소에서 색을 끌어와
    메운다. 화면 끝에 딱 붙이면 «Logo area is outside of the frame»으로 실패한다."""
    f = desub.delogo_filter((1082, 1125), 720, 1280)
    assert f.startswith("delogo=")
    nums = dict(kv.split("=") for kv in f[len("delogo="):].split(":"))
    x, y, w, h = (int(nums[k]) for k in ("x", "y", "w", "h"))
    assert x >= 1 and y >= 1
    assert x + w <= 720 - 1
    assert y + h <= 1280 - 1


def test_delogo_clamps_out_of_range_input():
    """화면 밖·거꾸로 값이 들어와도 ffmpeg에 이상한 명령을 보내지 않는다."""
    assert desub.delogo_filter((-50, 99999), 720, 1280)          # 잘라서라도 만든다
    box = desub.clamp_band((-50, 99999), 720, 1280)
    x, y, w, h = box
    assert y >= 1 and y + h <= 1279
    assert desub.clamp_band((100, 100), 720, 1280) is not None    # 최소 두께 보장


# ── 실제 렌더에서 지워지나 ──────────────────────────────────────
@requires_ffmpeg
def test_render_actually_removes_the_subtitle(subbed_video, tmp_path):
    """말이 아니라 **결과 화면**으로 확인 — 자막 자리의 글자 흔적 점수가 0이어야 한다."""
    from cutdaejang.core import edit_mode
    from cutdaejang.spec import Style, Subtitle

    band = desub.find_subtitle_band(str(subbed_video))
    assert band
    subs = [Subtitle(text="한국어 자막", start_us=0, end_us=2_000_000)]

    def render(ds, name):
        out = tmp_path / name
        edit_mode.render_edited(
            str(subbed_video), [Subtitle(text=s.text, start_us=s.start_us, end_us=s.end_us)
                                for s in subs],
            str(out), Style(size=64), layout="keep", desub=ds, quality="draft")
        return out

    off = render(None, "off.mp4")
    on = render(band, "on.mp4")

    def trace(video):
        """자막 자리에 남은 «글자 가장자리» 점수 — 찾을 때 쓴 것과 같은 잣대."""
        w = 160
        h = max(2, int(H * w / W)) & ~1
        frames = desub._gray_frames(str(video), w, h, 6, SEC)
        a, b = int(band[0] * h / H), int(band[1] * h / H)
        return sum(desub._row_scores(frames, w, h)[a:b])

    before, after = trace(off), trace(on)
    assert before > 100, f"시험 영상에 자막이 안 박혔음 (before={before})"
    assert after < before * 0.1, f"자막이 남아 있음: {before} → {after}"


# ── 화면·서버 배선 ─────────────────────────────────────────────
def test_edit_card_has_the_switch_and_preview():
    assert 'id="desubChk"' in HTML
    assert 'id="desubModeSel"' in HTML
    assert 'id="desubY0"' in HTML and 'id="desubY1"' in HTML
    assert "👁 어디를 지우는지 보기" in HTML       # 만들기 전에 눈으로 확인
    assert "자동으로 찾기 (권장)" in HTML
    assert "내가 직접 지정" in HTML
    # 배경이 복잡하면 번질 수 있다는 걸 숨기지 않는다
    assert "살짝 번질 수 있어요" in HTML


def test_desub_flows_from_form_to_render():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert "desub: !!(($('desubChk')||{}).checked)" in src        # 제출
    assert 'elif path == "/api/desub_preview":' in src            # 미리보기 경로
    assert "def _desub_preview(" in src
    assert "def _resolve_desub(" in src
    # 🔴 «여러 쇼츠로 나누기» 경로에서도 같은 값을 써야 한다 (한쪽에만 두면 이름을 못 찾아 터진다)
    assert src.count("desub=_resolve_desub(ep, clip_video, job_id)") == 1
    assert "desub=desub_band" in src


def test_desub_is_applied_before_resizing():
    """찾은 좌표는 **원본 픽셀 기준**이라 화면을 줄인 뒤에 걸면 엉뚱한 자리를 지운다."""
    src = (ROOT / "cutdaejang/core/edit_mode.py").read_text(encoding="utf-8")
    body = src.split("src_tag, pre_vf = ")[1][:600]
    assert 'pre_vf = f"[0:v]{dl}[dsv];"' in body
    assert 'src_tag = "[dsv]"' in body
    # 원본 태그를 쓰던 자리가 전부 교체됐는지
    after = src.split("src_tag, pre_vf = ")[1]
    assert 'f"{pre_vf}{src_tag}split=2[bg][fg];"' in after
    assert 'f"{pre_vf}{src_tag}scale=' in after


def test_preview_png_is_served_safely():
    """미리보기 그림 한 개만 내보낸다 — 경로 조작으로 아무 파일이나 열리면 안 된다."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src.split("def _serve_preview(")[1].split("\n    def ")[0]
    assert 'if name == "desub.png":' in body
    assert '"_preview" / "desub.png"' in body


def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML     # 판이 올라가도 안 깨지게
