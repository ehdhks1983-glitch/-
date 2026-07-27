"""v0.94 — 🎬 구간 이음새: 검은 깜빡임 제거(몽타주 하드컷) + 크로스페이드 말 보호 패딩."""

import re
import subprocess

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def _mk_clip(tmp_path, name, color, sec=3, audio=True):
    from cutdaejang.utils import ffmpeg as ff

    p = tmp_path / name
    args = [ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=30:d={sec}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}",
                 "-c:a", "aac", "-shortest"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p)]
    ff.run(args)
    return str(p)


def _black_periods(path):
    from cutdaejang.utils import ffmpeg as ff

    r = subprocess.run([ff.ffmpeg_bin(), "-i", str(path),
                        "-vf", "blackdetect=d=0.03:pix_th=0.15", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return re.findall(r"black_start:\S+", r.stderr)


@requires_ffmpeg
def test_montage_hard_cut_has_no_black_dips(tmp_path):
    """몽타주 조각 이음(transition=none)에서 검은 화면이 나오지 않는다.

    사용자 영상 blackdetect: 2.3초마다 0.07초 검은 깜빡임 — 조각별 fade가 원인.
    """
    from cutdaejang.core import video_editor

    src = _mk_clip(tmp_path, "src.mp4", "orange", sec=9)
    segs = [(0, 2_000_000), (3_000_000, 5_000_000), (6_000_000, 8_000_000)]
    out = video_editor.cut_and_concat(src, segs, str(tmp_path / "cut.mp4"),
                                      transition="none")
    assert _black_periods(out) == []
    # 회귀 확인용: 예전 fade 방식은 실제로 검은 구간을 만든다 (원인 재현)
    out2 = video_editor.cut_and_concat(src, segs, str(tmp_path / "cut_fade.mp4"),
                                       transition="fade")
    assert _black_periods(out2)


@requires_ffmpeg
def test_pad_video_adds_freeze_and_silence(tmp_path):
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    src = _mk_clip(tmp_path, "p.mp4", "teal", sec=2)
    out = video_editor.pad_video(src, str(tmp_path / "pad.mp4"),
                                 head_s=0.45, tail_s=0.45)
    dur = ff.probe_duration_us(out) / 1e6
    assert 2.7 <= dur <= 3.15, dur          # 2 + 0.45×2 ± 인코딩 오차
    assert ff.has_audio_stream(out)
    # 패딩 없음 → 원본 그대로 (재인코딩 안 함)
    assert video_editor.pad_video(src, str(tmp_path / "no.mp4")) == src


def test_sections_pipeline_wiring():
    src = open(webui.__file__, encoding="utf-8").read()
    # 몽타주는 하드컷 — 검은 깜빡임 원인 제거
    assert 'str(job_dir / f"sec_{i}_cut.mp4"), transition="none")' in src
    # v0.99: 패딩 제거 (이음새 1.5초 죽은 공백의 원인) — amix가 말을 보호한다
    assert "sec_pad_" not in src
    # 챕터는 경계당 −fade (패딩 없이 크로스페이드만큼 앞당겨짐)
    assert "cum += durs[k] - (fade if k < len(outs) - 1 else 0.0)" in src
    # 완료 화면 라벨 — 구간 합본은 쇼츠가 아니라 합본+구간 파일
    assert "최종 합본, 나머지는 구간별 파일" in webui._HTML
