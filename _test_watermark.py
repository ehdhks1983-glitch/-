"""
_test_watermark.py — 워터마크 엔진 + 전 경로 연동 검증 (ffmpeg 필요, display 불필요).
주의: watermark.save() 를 호출하지 않아 디스크(data/watermark.json)에 안 남김 → 다른 테스트 영향 없음.
"""
import sys, subprocess, traceback
from pathlib import Path
from PIL import Image

OUT = Path("_test_out"); OUT.mkdir(exist_ok=True)
ASSET = Path("_test_assets"); ASSET.mkdir(exist_ok=True)

results = []
def check(name, fn):
    try:
        fn(); results.append((name, True)); print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False)); print(f"  ❌ {name}: {e}"); traceback.print_exc()

from watermark import watermark, apply_to_frame, drawtext_filter

def _ink(img, box, thresh=100):
    return sum(1 for px in img.crop(box).convert("L").getdata() if px > thresh)

def t_disabled_noop():
    watermark.set("enabled", False)
    f = Image.new("RGB", (200, 200), (0, 0, 0))
    assert apply_to_frame(f) is f, "비활성인데 프레임이 바뀜"
    assert not watermark.active
    assert drawtext_filter(480) == ""
check("비활성 시 원본 그대로(no-op)", t_disabled_noop)

def t_text_wm():
    watermark.set("enabled", True); watermark.set("mode", "text")
    watermark.set("text", "@블로그ID"); watermark.set("position", "br"); watermark.set("opacity", 80)
    assert watermark.active
    out = apply_to_frame(Image.new("RGB", (600, 400), (0, 0, 0)))
    assert _ink(out, (380, 300, 600, 400)) > 50, "우측하단 텍스트 워터마크 안 보임"
check("텍스트 워터마크 합성 (우측 하단)", t_text_wm)

def t_logo_wm():
    logo = Image.new("RGBA", (120, 120), (255, 0, 0, 255)); logo.save(ASSET / "logo.png")
    watermark.set("mode", "image"); watermark.set("image_path", str(ASSET / "logo.png"))
    watermark.set("scale", 20); watermark.set("position", "tl")
    out = apply_to_frame(Image.new("RGB", (600, 400), (0, 0, 0))).convert("RGB")
    red = sum(1 for px in out.crop((0, 0, 200, 200)).getdata() if px[0] > 120 and px[1] < 80)
    assert red > 50, "좌측상단 로고 워터마크 안 보임"
check("로고 이미지 워터마크 합성 (좌측 상단)", t_logo_wm)

def t_ffmpeg_filter():
    watermark.set("mode", "text"); watermark.set("text", "한글워터마크"); watermark.set("position", "br")
    f = drawtext_filter(480)
    assert f.startswith("drawtext=") and "fontsize" in f and "x=w-tw" in f
check("영상용 drawtext 필터 생성", t_ffmpeg_filter)

def t_merge_with_wm():
    watermark.set("mode", "text"); watermark.set("text", "@blog"); watermark.set("position", "br")
    from image_merger import MergeJob, merge_images
    imgs = []
    for i, c in enumerate(["white", "white"]):
        p = ASSET / f"wm{i}.png"; Image.new("RGB", (400, 300), c).save(p); imgs.append(str(p))
    job = MergeJob(); job.image_paths = imgs; job.output_format = "gif"
    job.resize_mode = "none"; job.output_path = str(OUT / "wm_merge.gif")
    r = merge_images(job)
    assert r and Path(r).exists(), "워터마크 합치기 실패"
    # 첫 프레임 우측하단에 워터마크 잉크(흰 배경에 검정 외곽선 텍스트)
    im = Image.open(r); im.seek(0)
    dark = sum(1 for px in im.convert("L").crop((250, 220, 400, 300)).getdata() if px < 80)
    assert dark > 20, "합쳐진 GIF에 워터마크 안 보임"
    im.close()
check("이미지 합치기 결과에 워터마크 적용", t_merge_with_wm)

def t_video_with_wm():
    watermark.set("mode", "text"); watermark.set("text", "@blog")
    src = ASSET / "wmv.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                    "-pix_fmt", "yuv420p", str(src)], capture_output=True)
    from video_converter import ConvertJob, convert_video
    job = ConvertJob(); job.input_path = str(src); job.output_path = str(OUT / "wm_vid.gif")
    job.output_format = "gif"; job.fps = 10; job.width = 240
    r = convert_video(job)
    assert r and Path(r).exists() and Path(r).stat().st_size > 0, "워터마크 영상 변환 실패"
check("영상→GIF 변환에 텍스트 워터마크 적용", t_video_with_wm)

# 정리(메모리만, 디스크 저장 안 함)
watermark.set("enabled", False)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
