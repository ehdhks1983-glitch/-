"""v1.30 — 목록 60: 「목소리만 다시」가 처음부터 다시 만드는 것만큼 오래 걸리던 것.

회원님 24차:
> "아니 점점 너가 봤을 때 최선책이 있을 거 아니야? 시간이 오래 걸리면 당연히 안 되는
>  거고, 편집인데 나레이션 하나 바꾸는 게 오래 걸리면 다른 프로그램이랑 차별점을
>  떠나서 더 후져지는 건데"

맞는 말씀이다. v1.29의 「목소리만 다시」는 **화면을 처음부터 다시 구웠다** —
목소리 하나 바꾸는 데 4K 2분짜리가 9분(실측 535초). 그건 부분 수정이 아니다.

**자막은 이미 화면에 구워져 있다.** 그러니 자막 시각을 그대로 두는 한 화면을
다시 만들 이유가 없다 — `-c:v copy`로 소리만 갈아 끼우면 된다. 실측 **82배**.
"""

import re
import subprocess
import time
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang.core import edit_mode
from cutdaejang.gui import webui
from cutdaejang.spec import Style, Subtitle
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

SRC = (Path(__file__).resolve().parents[1] / "cutdaejang/gui/webui.py").read_text(
    encoding="utf-8")
TOTAL_US = 12_000_000
SUBS = [Subtitle(text=f"{i + 1}번째 문장이에요", start_us=i * 3_000_000,
                 end_us=i * 3_000_000 + 2_600_000) for i in range(4)]


def test_version():
    assert __version__ == "1.46.0"


@pytest.fixture(scope="module")
def tone(tmp_path_factory):
    d = tmp_path_factory.mktemp("revoice")

    def make(sec, freq, name):
        p = d / name
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"sine=f={freq}:d={sec}", str(p)])
        return p

    return d, make


@pytest.fixture(scope="module")
def done_video(tone):
    """완성된 4K 영상 한 벌 — 자막이 화면에 구워져 있다."""
    d, make = tone
    pic = d / "pic.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "gradients=size=1080x1920:duration=12:rate=30:speed=0.02",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(pic)])
    old = [make(2.4, 300, f"o{i}.wav") for i in range(4)]
    narr = edit_mode.build_narration_wav(old, SUBS, TOTAL_US, str(d / "old.wav"))
    return edit_mode.render_edited(
        str(pic), SUBS, str(d / "done.mp4"), Style(size=64), layout="shorts",
        quality="ultra", narration_wav=narr, orig_audio="mute")


def _video_hash(path: str) -> str:
    """화면(비디오 스트림)만의 해시 — 소리를 바꿔도 이게 같으면 안 건드린 것."""
    out = subprocess.run(
        [ff.ffmpeg_bin(), "-v", "error", "-i", str(path), "-map", "0:v",
         "-c", "copy", "-f", "md5", "-"],
        capture_output=True, timeout=120, check=True)
    return out.stdout.decode().strip()


# ── 칸에 맞추기 ────────────────────────────────────────────────
@requires_ffmpeg
def test_short_clips_are_left_alone(tone):
    """칸보다 짧으면 손대지 않는다 — 남는 자리는 그냥 조용하다."""
    d, make = tone
    clips = [make(2.0, 400, f"s{i}.wav") for i in range(4)]
    fitted, why = edit_mode.fit_clips_to_slots(clips, SUBS, TOTAL_US, d / "fs")
    assert not why and fitted == clips        # 파일을 새로 만들지도 않았다


@requires_ffmpeg
def test_slightly_long_clips_are_gently_sped_up(tone):
    """살짝 길면 그 문장만 조금 빠르게 — 티가 안 나는 선에서."""
    d, make = tone
    clips = [make(3.4, 400, f"m{i}.wav") for i in range(4)]
    fitted, why = edit_mode.fit_clips_to_slots(clips, SUBS, TOTAL_US, d / "fm")
    assert not why
    for f in fitted:
        assert ff.probe_duration_us(str(f)) <= 3_100_000, "칸을 넘으면 다음 문장과 겹친다"


@requires_ffmpeg
def test_far_too_long_gives_up_instead_of_mangling_the_voice(tone):
    """🔴 여기서 욕심내면 안 된다.

    1.5배로 억지로 줄이면 말이 우스워진다. 빠른 게 목적이지 망치는 게 목적이 아니다
    — 못 맞추면 «못 맞춘다»고 답하고 화면부터 다시 굽는 게 맞다.
    """
    d, make = tone
    clips = [make(4.6, 400, f"L{i}.wav") for i in range(4)]
    fitted, why = edit_mode.fit_clips_to_slots(clips, SUBS, TOTAL_US, d / "fL")
    assert fitted is None
    assert "1번째 문장" in why and "안 들어가요" in why


def test_mismatched_counts_are_refused():
    fitted, why = edit_mode.fit_clips_to_slots(["a"], SUBS, TOTAL_US, "/tmp")
    assert fitted is None and "문장 수" in why


# ── 소리만 갈아 끼우기 ─────────────────────────────────────────
@requires_ffmpeg
def test_swapping_the_voice_does_not_touch_a_single_frame(done_video, tone):
    """🔴 이번 판의 핵심 — 화면(비디오 스트림)이 **바이트 단위로 같아야** 한다.

    같다는 건 다시 굽지 않았다는 뜻이고, 그래서 4K든 8K든 몇 초에 끝난다.
    """
    d, make = tone
    clips = [make(2.2, 700, f"v{i}.wav") for i in range(4)]
    fitted, why = edit_mode.fit_clips_to_slots(clips, SUBS, TOTAL_US, d / "fv")
    assert not why
    narr = edit_mode.build_narration_wav(fitted, SUBS, TOTAL_US, str(d / "new.wav"))

    t0 = time.monotonic()
    out = edit_mode.swap_narration(done_video, str(d / "swap.mp4"), narr)
    took = time.monotonic() - t0

    assert _video_hash(out) == _video_hash(done_video), "화면이 다시 구워졌다"
    assert ff.probe_video_size(out) == ff.probe_video_size(done_video)
    assert abs(ff.probe_duration_us(out) - TOTAL_US) < 400_000
    assert took < 25, f"소리만 바꾸는데 {took:.0f}초나 걸렸다"


@requires_ffmpeg
def test_the_new_voice_actually_replaced_the_old_one(done_video, tone):
    """화면이 그대로인 건 좋지만 **소리는 진짜 바뀌어야** 한다."""
    d, make = tone
    clips = [make(2.2, 900, f"z{i}.wav") for i in range(4)]
    fitted, _ = edit_mode.fit_clips_to_slots(clips, SUBS, TOTAL_US, d / "fz")
    narr = edit_mode.build_narration_wav(fitted, SUBS, TOTAL_US, str(d / "z.wav"))
    out = edit_mode.swap_narration(done_video, str(d / "swapz.mp4"), narr)

    def audio_md5(p):
        r = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-i", str(p), "-map", "0:a",
             "-f", "md5", "-"], capture_output=True, timeout=120, check=True)
        return r.stdout.decode().strip()

    assert audio_md5(out) != audio_md5(done_video), "소리가 안 바뀌었다"


@requires_ffmpeg
def test_bgm_is_mixed_the_same_way_as_a_full_render(done_video, tone):
    """BGM 크기 식을 따로 적으면 다시 만든 영상과 소리 크기가 달라진다."""
    d, make = tone
    bgm = make(30, 220, "bgm.wav")
    clips = [make(2.2, 700, f"b{i}.wav") for i in range(4)]
    fitted, _ = edit_mode.fit_clips_to_slots(clips, SUBS, TOTAL_US, d / "fb")
    narr = edit_mode.build_narration_wav(fitted, SUBS, TOTAL_US, str(d / "b.wav"))
    out = edit_mode.swap_narration(done_video, str(d / "swapb.mp4"), narr,
                                   bgm_path=str(bgm), bgm_db=-16.0)
    assert Path(out).is_file() and ff.probe_duration_us(out) > 0
    # 렌더와 «같은 함수»로 BGM 소리를 만든다 (식을 두 군데 적으면 어긋난다)
    src = (Path(edit_mode.__file__)).read_text(encoding="utf-8")
    assert src.count("def _bgm_filter(") == 1
    assert src.count("_bgm_filter(") == 3        # 정의 + 렌더 + 소리교체
    assert src.count('sidechaincompress=') == 1  # 덕킹 식도 한 곳에만


# ── 서버 배선 ─────────────────────────────────────────────────
def test_revoice_tries_the_fast_path_first_then_falls_back():
    body = SRC.split("def _run_revoice(")[1].split("\ndef ")[0]
    assert "_fast_revoice(job_id, src_id, params, workdir)" in body
    assert "_run_edit(job_id, params, workdir)" in body, "빠른 길이 막히면 결과가 안 나온다"
    # 빠른 길이 어떤 식으로 실패해도 회원님은 결과를 받아야 한다
    assert "except Exception as e:" in body


def test_fast_path_refuses_the_cases_it_cannot_do_exactly():
    body = SRC.split("def _fast_revoice(")[1].split("\ndef ")[0]
    for mark in ("완성된 영상 파일이 없어요", "자막 시각이 남아 있지 않아요",
                 "원본 소리를 함께 쓰는 영상이에요", "배속이 걸린 영상이에요"):
        assert mark in body, f"«{mark}» 검사가 없다 — 틀린 소리가 나올 수 있다"
    assert "edit_mode.fit_clips_to_slots(" in body
    assert "edit_mode.swap_narration(" in body


def test_both_paths_make_the_voice_the_same_way():
    """빠른 길과 느린 길이 다른 방식으로 합성하면 소리 결이 달라진다."""
    assert SRC.count("def _synth_narration_clips(") == 1
    assert SRC.count("_synth_narration_clips(") == 3   # 정의 + 렌더 + 빠른 길
    assert "_queue_job(new_id, _run_revoice, new_id, src_id, new_params, workdir)" in SRC


def test_html_is_still_well_formed():
    html = webui._apply_links(webui._HTML)
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", html)) == len(
            re.findall(rf"</{tag}>", html)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in html
