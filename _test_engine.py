"""
_test_engine.py — 엔진(비-GUI) 기능 검증. 실제 이미지/영상으로 변환을 돌려본다.
display 불필요. 통과하면 코어 로직이 살아있다는 의미.
"""
import os
import sys
import subprocess
import traceback
from pathlib import Path

OUT = Path("_test_out")
OUT.mkdir(exist_ok=True)
ASSET = Path("_test_assets")
ASSET.mkdir(exist_ok=True)

results = []
def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False, traceback.format_exc()))
        print(f"  ❌ {name}: {e}")

# ── 테스트 이미지 생성 ──
from PIL import Image, ImageDraw
img_paths = []
for i, (w, h, color) in enumerate([(400, 300, "red"), (500, 350, "green"), (450, 320, "blue")]):
    p = ASSET / f"img{i}.png"
    im = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, w-20, h-20], outline="white", width=5)
    d.text((w//2, h//2), f"{i+1}", fill="white")
    im.save(p)
    img_paths.append(str(p))
print(f"테스트 이미지 {len(img_paths)}장 생성")

# ── 테스트 영상 생성 (오디오 포함) ──
test_video = ASSET / "test.mp4"
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
    "-pix_fmt", "yuv420p", "-shortest", str(test_video)
], capture_output=True)
print(f"테스트 영상 생성: {test_video.exists()}")

print("\n── 엔진 테스트 ──")

# utils
def t_utils():
    import utils
    assert utils.is_image_file("a.png")
    assert utils.is_video_file("a.mp4")
    assert "KB" in utils.format_filesize(2048)
    assert utils.find_ffmpeg() is not None
    info = utils.get_image_info(img_paths[0])
    assert info and info[0] == 400
check("utils 기본 함수", t_utils)

# image_merger
def t_merge_gif():
    from image_merger import MergeJob, merge_images
    job = MergeJob()
    job.image_paths = img_paths
    job.output_format = "gif"
    job.default_delay = 200
    job.resize_mode = "fixed_width"
    job.custom_width = 320
    job.output_path = str(OUT / "merge.gif")
    r = merge_images(job)
    assert r and Path(r).exists() and Path(r).stat().st_size > 0
check("이미지 합치기 → GIF", t_merge_gif)

def t_merge_webp_subtitle():
    from image_merger import MergeJob, merge_images
    job = MergeJob()
    job.image_paths = img_paths
    job.output_format = "webp"
    job.text_overlays = [{"text": "테스트", "position": "bottom", "size": 28, "color": "#FFFF00", "bold": True}]
    job.output_path = str(OUT / "merge_sub.webp")
    r = merge_images(job)
    assert r and Path(r).exists()
check("이미지 합치기 → WebP + 자막", t_merge_webp_subtitle)

# editor
def t_editor():
    from editor import load_frames, save_frames, apply_edits
    frames, durations, loop = load_frames(str(OUT / "merge.gif"))
    assert len(frames) == 3
    edits = {"crop_ratio": "1:1", "resize_percent": 50, "grayscale": True, "speed": 2.0, "boomerang": True}
    ef, ed = apply_edits([f.copy() for f in frames], list(durations), edits)
    save_frames(ef, ed, str(OUT / "edited.gif"), "gif", loop)
    assert Path(OUT / "edited.gif").exists()
check("편집(크롭/리사이즈/흑백/속도/부메랑)", t_editor)

# optimizer
def t_optimizer():
    from optimizer import auto_optimize
    r = auto_optimize(str(OUT / "merge.gif"), target_size_kb=10)
    assert r is not None
check("최적화 auto_optimize", t_optimizer)

# video_converter
def t_probe():
    from video_converter import probe_video
    info = probe_video(str(test_video))
    assert info and info.width == 320 and info.duration > 1.5
    assert info.has_audio
check("영상 probe (해상도/길이/오디오)", t_probe)

def t_video_gif():
    from video_converter import ConvertJob, convert_video
    job = ConvertJob()
    job.input_path = str(test_video)
    job.output_path = str(OUT / "video.gif")
    job.output_format = "gif"
    job.fps = 10
    job.width = 240
    r = convert_video(job)
    assert r and Path(r).exists() and Path(r).stat().st_size > 0
check("영상 → GIF (2-pass 팔레트)", t_video_gif)

def t_video_sub():
    from video_converter import ConvertJob, convert_video, Subtitle
    job = ConvertJob()
    job.input_path = str(test_video)
    job.output_path = str(OUT / "video_sub.webp")
    job.output_format = "webp"
    job.fps = 10
    job.subtitles = [Subtitle(text="안녕", start=0, end=2, position="bottom", size=32, color="#FFFFFF")]
    r = convert_video(job)
    assert r and Path(r).exists()
check("영상 → WebP + 자막(drawtext)", t_video_sub)

# ── 결과 ──
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n{'='*40}\n결과: {passed}/{total} 통과")
for name, ok, tb in results:
    if not ok:
        print(f"\n❌ {name}\n{tb}")
sys.exit(0 if passed == total else 1)
