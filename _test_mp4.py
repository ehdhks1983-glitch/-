"""
_test_mp4.py — MP4/쇼츠 출력 엔진 검증 (ffmpeg 필요, display 불필요).
ffprobe로 결과물의 해상도/코덱/오디오 유무를 직접 확인한다.
"""
import sys, json, subprocess, traceback
from pathlib import Path

OUT = Path("_test_out"); OUT.mkdir(exist_ok=True)
ASSET = Path("_test_assets"); ASSET.mkdir(exist_ok=True)

# 오디오 포함 테스트 영상 (320x240, 2초)
src = ASSET / "mp4src.mp4"
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
    "-pix_fmt", "yuv420p", "-shortest", str(src)
], capture_output=True)

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_streams", "-show_format", str(path)], capture_output=True)
    return json.loads(r.stdout.decode())

def streams_of(path, ctype):
    return [s for s in probe(path)["streams"] if s.get("codec_type") == ctype]

results = []
def check(name, fn):
    try:
        fn(); results.append((name, True)); print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False)); print(f"  ❌ {name}: {e}"); traceback.print_exc()

from video_converter import ConvertJob, convert_video, Subtitle

def t_mp4_basic():
    job = ConvertJob()
    job.input_path = str(src); job.output_path = str(OUT / "out.mp4")
    job.output_format = "mp4"; job.fps = 15; job.width = 240
    r = convert_video(job)
    assert r and Path(r).exists() and Path(r).stat().st_size > 0
    v = streams_of(r, "video"); a = streams_of(r, "audio")
    assert v and v[0]["codec_name"] == "h264", "비디오 코덱 아님"
    assert a and a[0]["codec_name"] == "aac", "오디오(aac) 누락"
    assert int(v[0]["width"]) % 2 == 0 and int(v[0]["height"]) % 2 == 0, "홀수 해상도"
    print(f"       일반 MP4: {v[0]['width']}x{v[0]['height']}, 오디오 OK")

def t_mp4_shorts():
    job = ConvertJob()
    job.input_path = str(src); job.output_path = str(OUT / "shorts.mp4")
    job.output_format = "mp4"; job.fps = 15
    job.shorts_vertical = True
    r = convert_video(job)
    assert r and Path(r).exists()
    v = streams_of(r, "video")
    assert v and int(v[0]["width"]) == 1080 and int(v[0]["height"]) == 1920, \
        f"쇼츠 해상도 {v[0]['width']}x{v[0]['height']} (1080x1920 아님)"
    assert streams_of(r, "audio"), "쇼츠 오디오 누락"
    print(f"       쇼츠 MP4: 1080x1920 세로, 오디오 OK")

def t_mp4_speed_audio():
    job = ConvertJob()
    job.input_path = str(src); job.output_path = str(OUT / "fast.mp4")
    job.output_format = "mp4"; job.fps = 15; job.width = 240
    job.speed = 2.0  # 2배속 → atempo 경로
    r = convert_video(job)
    assert r and Path(r).exists()
    dur = float(probe(r)["format"]["duration"])
    assert dur < 1.5, f"2배속인데 길이 {dur:.2f}s (1초 근처여야)"
    assert streams_of(r, "audio"), "속도변경 오디오 누락"
    print(f"       2배속 MP4: {dur:.2f}초, 오디오(atempo) OK")

def t_mp4_subtitle():
    job = ConvertJob()
    job.input_path = str(src); job.output_path = str(OUT / "subs.mp4")
    job.output_format = "mp4"; job.fps = 15; job.shorts_vertical = True
    job.subtitles = [Subtitle(text="쇼츠 자막", start=0, end=2, position="bottom", size=40, color="#FFFF00")]
    r = convert_video(job)
    assert r and Path(r).exists(), "자막+쇼츠 변환 실패"
    print("       쇼츠+자막 합성 OK")

check("일반 MP4 (H.264+AAC, 짝수 해상도, 오디오 유지)", t_mp4_basic)
check("쇼츠 MP4 (세로 1080x1920 + 오디오)", t_mp4_shorts)
check("2배속 MP4 (atempo 오디오)", t_mp4_speed_audio)
check("쇼츠 + 자막 합성", t_mp4_subtitle)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
