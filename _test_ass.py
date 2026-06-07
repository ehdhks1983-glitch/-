"""
_test_ass.py — ASS 전문 자막 검증 (ffmpeg+libass 필요).
자막이 '실제로 영상 위에 그려지는지' 픽셀로 확인한다.
"""
import sys, json, subprocess, traceback
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

import shorts_maker as sm
ff = sm.find_ffmpeg()

def t_libass():
    assert sm._filter_available(ff, "subtitles"), "이 ffmpeg에 libass(subtitles) 없음"
check("libass(subtitles) 필터 사용 가능", t_libass)

def t_ass_file():
    ev = [(0.0, 2.0, "첫 자막"), (2.0, 4.0, "두 번째 자막")]
    p = OUT / "cap.ass"
    sm._build_ass_file(ev, str(p), sm._ass_font(), 56)
    txt = p.read_text(encoding="utf-8")
    assert "[V4+ Styles]" in txt and "Style: Pop" in txt
    assert txt.count("Dialogue:") == 2
    assert "fad" in txt and "fscx" in txt  # 애니메이션 태그
check("ASS 파일 생성(스타일+애니메이션 태그)", t_ass_file)

def t_caption_visible():
    """검정 영상에 흰 자막 번인 → 자막 영역에 밝은 픽셀이 실제로 생기는지"""
    blk = ASSET / "blk.mp4"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=2",
                    "-pix_fmt", "yuv420p", str(blk)], capture_output=True)
    ev = [(0.0, 2.0, "자막 테스트")]
    sm._build_ass_file(ev, str(ASSET / "cap.ass"), sm._ass_font(), 80)
    out = OUT / "burned.mp4"
    # 작업폴더 기준 상대경로(앱과 동일 방식)
    sm._run([ff, "-y", "-i", "blk.mp4", "-filter_complex", "[0:v]subtitles=cap.ass[v]",
             "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out.resolve())],
            timeout=120, cwd=str(ASSET))
    assert out.exists(), "자막 번인 실패"
    # t=1s 프레임 추출 → 하단 자막영역 밝은 픽셀 확인
    fr = OUT / "fr.png"
    subprocess.run([ff, "-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(fr)],
                   capture_output=True)
    im = Image.open(fr).convert("L")
    region = im.crop((200, 1350, 880, 1750))  # 하단 중앙(자막 위치)
    bright = sum(1 for px in region.getdata() if px > 180)
    assert bright > 200, f"자막이 화면에 안 보임 (밝은 픽셀 {bright})"
    print(f"       자막 영역 밝은 픽셀: {bright} (정상적으로 렌더됨)")
    im.close()
check("자막이 실제로 영상에 보이게 렌더됨 (픽셀 확인)", t_caption_visible)

def t_full_shorts_ass():
    imgs = []
    for i, c in enumerate(["#225", "#522"]):
        p = ASSET / f"as{i}.png"; Image.new("RGB", (800, 600), c).save(p); imgs.append(str(p))
    proj = sm.ShortsProject()
    proj.segments = [sm.ShortsSegment(image_path=imgs[0], duration=2, caption="첫 장면 자막", narration="첫 장면", template="blur"),
                     sm.ShortsSegment(image_path=imgs[1], duration=2, caption="둘째 장면 자막", narration="", template="fill")]
    proj.output_path = str(OUT / "ass_shorts.mp4")
    r = sm.build_shorts(proj)
    assert r and Path(r).exists(), "쇼츠 빌드 실패"
    streams = json.loads(subprocess.run(
        [ff.replace("ffmpeg", "ffprobe") if "ffmpeg" in ff else "ffprobe",
         "-v", "quiet", "-print_format", "json", "-show_streams", r],
        capture_output=True).stdout or b'{"streams":[]}')["streams"]
    v = [s for s in streams if s["codec_type"] == "video"]
    assert v and int(v[0]["height"]) == 1920, "세로 1080x1920 아님"
check("전체 쇼츠 빌드 (ASS 자막 경로)", t_full_shorts_ass)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
