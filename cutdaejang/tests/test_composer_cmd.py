"""ffmpeg_composer.build_command 순수 함수 검증 (실행 없음)."""

from cutdaejang.core.render_engine.ffmpeg_composer import RenderOptions, build_command
from cutdaejang.spec import MainVideo
from cutdaejang.utils.ffmpeg import escape_filter_value
from tests.test_spec import make_valid_spec


def _cmd_str(spec, **kw) -> str:
    defaults = dict(
        voice_path="voice.m4a", ass_path="subs.ass", out_path="out.mp4",
        fonts_dir="/fonts",
    )
    defaults.update(kw)
    return " ".join(map(str, build_command(spec, **defaults)))


def test_image_background_no_main_video():
    spec = make_valid_spec()
    spec.style.gradient_overlay = False
    cmd = _cmd_str(spec)

    assert "-loop 1 -t 5.000000 -i bg.png" in cmd
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in cmd
    assert "overlay" not in cmd  # 정보형 쇼츠: 배경+자막만
    assert "subtitles=filename='subs.ass':fontsdir='/fonts'" in cmd
    assert "-c:v libx264 -crf 19 -preset medium" in cmd
    assert "-map [v] -map 1:a" in cmd
    assert "-movflags +faststart" in cmd
    assert "-t 5.000000 out.mp4" in cmd


def test_gradient_overlay_added_after_main():
    spec = make_valid_spec()
    spec.style.gradient_overlay = True
    cmd = _cmd_str(spec, gradient_path="grad.png")
    assert "[bg][2:v]overlay=x=0:y=0[grad]" in cmd
    assert "[grad]subtitles=" in cmd


def test_main_video_top_layout_freeze_last():
    spec = make_valid_spec()
    spec.style.gradient_overlay = False
    spec.main_video = MainVideo(path="main.mp4", layout="top", scale=0.9)
    cmd = _cmd_str(spec, main_video_duration_us=3_000_000)  # spec 5초보다 짧음

    assert "tpad=stop_mode=clone:stop_duration=2.000000" in cmd
    assert "scale=972:-2" in cmd  # 1080*0.9=972 (짝수 보정 불필요)
    assert "overlay=x=(W-w)/2:y=154" in cmd  # 1920*0.08=153.6 → round 154


def test_main_video_longer_gets_trimmed():
    spec = make_valid_spec()
    spec.main_video = MainVideo(path="main.mp4", layout="center", scale=0.9)
    cmd = _cmd_str(spec, main_video_duration_us=9_000_000, gradient_path=None)
    assert "trim=duration=5.000000,setpts=PTS-STARTPTS" in cmd
    assert "tpad" not in cmd
    assert "overlay=x=(W-w)/2:y=(H-h)/2" in cmd


def test_main_video_loop_policy_uses_stream_loop():
    spec = make_valid_spec()
    spec.main_video = MainVideo(path="main.mp4", layout="full", scale=0.9,
                                short_policy="loop")
    cmd = _cmd_str(spec, main_video_duration_us=2_000_000)
    assert "-stream_loop -1 -i main.mp4" in cmd
    assert "trim=duration=5.000000" in cmd
    assert "crop=1080:1920" in cmd  # full: 캔버스 커버


def test_nvenc_encoder_maps_crf_to_cq():
    spec = make_valid_spec()
    cmd = _cmd_str(spec, encoder="h264_nvenc", opts=RenderOptions(crf=23, preset="slow"))
    assert "-c:v h264_nvenc -preset p6 -rc vbr -cq 23 -b:v 0" in cmd
    assert "libx264" not in cmd


def test_color_background_uses_lavfi():
    spec = make_valid_spec()
    spec.background.type = "color"
    spec.background.path = None
    spec.background.color = "#101020"
    cmd = _cmd_str(spec)
    assert "-f lavfi -i color=c=0x101020:s=1080x1920:r=30:d=5.000000" in cmd


def test_escape_filter_value_windows_path():
    # 드라이브 콜론은 따옴표 안이라도 \: 로 이스케이프해야 한다 (Windows 실기 확인)
    assert escape_filter_value(r"C:\작업 폴더\subs.ass") == r"'C\:/작업 폴더/subs.ass'"
    assert (
        escape_filter_value(r"C:\Users\김예준\Downloads\컷대장_v0.1\cutdaejang\resources\fonts")
        == r"'C\:/Users/김예준/Downloads/컷대장_v0.1/cutdaejang/resources/fonts'"
    )
    assert escape_filter_value("it's.ass") == r"'it'\''s.ass'"
    assert escape_filter_value("render/subs.ass") == "'render/subs.ass'"
