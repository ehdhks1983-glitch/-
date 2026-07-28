"""v0.99 — 🔊 이음새 소리 제자리 겹침(amix) + 🖼 가로 사진 블러 맞춤 + 🟢 태그 #."""

import re
import subprocess

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def _mk_tone_clip(tmp_path, name, tone_s=1.0, tail_s=1.0):
    """말(사인톤 tone_s초) + 꼬리 무음(tail_s초) — 구간 클립의 소리 구조 재현."""
    from cutdaejang.utils import ffmpeg as ff

    p = tmp_path / name
    total = tone_s + tail_s
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=navy:s=320x180:r=30:d={total}",
            "-f", "lavfi", "-i",
            f"sine=frequency=600:duration={tone_s}",
            "-af", f"apad=pad_dur={tail_s},aformat=channel_layouts=stereo",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(p)])
    return str(p)


def _mean_db(path, start, dur):
    from cutdaejang.utils import ffmpeg as ff

    r = subprocess.run([ff.ffmpeg_bin(), "-i", str(path),
                        "-af", f"atrim={start}:{start + dur},volumedetect",
                        "-vn", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    assert m, r.stderr[-400:]
    return float(m.group(1))


@requires_ffmpeg
def test_join_audio_keeps_full_volume(tmp_path):
    """이음새에서 뒷클립 첫 소리가 볼륨 깎임 없이 그대로 나온다 (acrossfade 폐지).

    사용자 실측: 구간 경계마다 1.5초 죽은 공백 + 첫마디 페이드인 — amix 전환으로
    뒷클립 소리는 제 위치에서 원래 볼륨. (A=톤1s+무음1s, B=톤부터 시작, 겹침 0.4s
    → B 톤은 1.6s 지점에서 시작해 즉시 최대 볼륨이어야 한다)
    """
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    a = _mk_tone_clip(tmp_path, "a.mp4")
    b = _mk_tone_clip(tmp_path, "b.mp4")
    base = _mean_db(b, 0.05, 0.25)              # 원본 톤 볼륨 (기준)
    out = video_editor.concat_videos([a, b], str(tmp_path / "j.mp4"),
                                     crossfade_s=0.4, transition="fade")
    total = ff.probe_duration_us(out) / 1e6
    assert 3.35 <= total <= 3.9, total          # 2+2−0.4 ± 인코딩 오차
    # B의 톤 시작 직후 0.25초 — 페이드인이었다면 크게 깎였을 창.
    # 원본 대비 2.5dB 안쪽이어야 '볼륨 그대로' (acrossfade면 10dB 이상 깎임)
    loud = _mean_db(out, 1.65, 0.25)
    assert loud > base - 2.5, f"이음새 볼륨이 깎임: {loud}dB (원본 {base}dB)"
    # 이음새 직전(둘 다 무음 구간)은 조용해야 정상 — 잡음 유입 없음
    quiet = _mean_db(out, 1.30, 0.25)
    assert quiet < -45, f"이음새 무음 구간에 잡음: {quiet}dB"


@requires_ffmpeg
def test_wide_photo_gets_blur_pad_on_vertical_canvas(tmp_path):
    """가로(16:9) 사진을 세로 캔버스에 — 크롭 대신 전체가 보이고 위아래 블러.

    좌우 끝을 빨강/파랑으로 칠한 가로 사진: 크롭이면 좌우가 잘려 빨강이 사라지고,
    블러 맞춤이면 중앙 높이 왼쪽 끝에서 빨강이 보인다.
    """
    from cutdaejang.core.background_generator import scene_slideshow, _mismatched_aspect
    from cutdaejang.spec import Canvas
    from cutdaejang.utils import ffmpeg as ff

    img = tmp_path / "wide.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i",
            "color=c=white:s=640x360,drawbox=x=0:y=0:w=60:h=360:c=red:t=fill,"
            "drawbox=x=580:y=0:w=60:h=360:c=blue:t=fill",
            "-frames:v", "1", str(img)])
    assert _mismatched_aspect(str(img), 360, 640) is True
    out = tmp_path / "slide.mp4"
    scene_slideshow([(str(img), 2_000_000)], str(out),
                    Canvas(w=360, h=640, fps=30), motion="none")
    # 중앙 높이 왼쪽 가장자리 4×4 픽셀 — 빨강 계열이면 원본 폭이 살아 있는 것
    r = subprocess.run([ff.ffmpeg_bin(), "-v", "error", "-i", str(out),
                        "-vf", "select=eq(n\\,15),crop=4:4:1:318",
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    px = r.stdout
    assert len(px) >= 48, r.stderr[-300:]
    reds = px[0::3][:16]
    blues = px[2::3][:16]
    assert sum(reds) / 16 > 120 and sum(blues) / 16 < 110, \
        (sum(reds) / 16, sum(blues) / 16)


def test_mismatched_aspect_keeps_ai_images_cover(tmp_path):
    """캔버스 비율로 생성된 AI 장면 그림은 기존처럼 꽉 채운다 (오탐 방지)."""
    from cutdaejang.core.background_generator import _mismatched_aspect
    from cutdaejang.utils import ffmpeg as ff

    img = tmp_path / "match.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=gray:s=540x960",
            "-frames:v", "1", str(img)])
    assert _mismatched_aspect(str(img), 1080, 1920) is False
    assert _mismatched_aspect("없는파일.png", 1080, 1920) is False   # 실패 시 기존 방식


def test_naver_clip_tags_have_hash():
    """네이버 클립 태그는 '#태그 #태그' 형식이어야 태그란이 인식한다."""
    html = webui._HTML
    idx = html.find("kitNaverTags')).value")
    seg = html[idx:idx + 200] if idx >= 0 else html
    assert "'#' + String(t).replace(/^#/, '')" in seg
    assert ".join(' ')" in seg
