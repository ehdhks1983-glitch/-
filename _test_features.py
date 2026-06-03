"""
_test_features.py — 새로 추가한 기능들의 엔진 검증 (display 불필요).
"""
import sys, traceback
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

# 소스 GIF 준비 (긴 5초짜리 — 3초 트림 확인용)
from image_merger import MergeJob, merge_images
src = OUT / "kakao_src.gif"
def _mk():
    job = MergeJob()
    imgs = []
    for i, c in enumerate(["red", "green", "blue", "orange", "purple"]):
        p = ASSET / f"k{i}.png"
        Image.new("RGB", (600, 400), c).save(p)  # 가로로 긴 직사각형
        imgs.append(str(p))
    job.image_paths = imgs
    job.output_format = "gif"
    job.default_delay = 1000  # 프레임당 1초 → 총 5초
    job.output_path = str(src)
    merge_images(job)
_mk()

def t_kakao_basic():
    from editor import make_kakao_emoticon
    out = str(OUT / "emoticon.webp")
    r = make_kakao_emoticon(str(src), out)
    assert r and Path(r).exists(), "출력 없음"
    im = Image.open(r)
    assert im.format == "WEBP", f"포맷 {im.format}"
    assert im.size == (360, 360), f"크기 {im.size}"  # 정사각형 360
    # 총 길이 ≤ 3초 (1초 프레임 → 최대 3프레임)
    n = getattr(im, "n_frames", 1)
    assert n <= 3, f"프레임수 {n} (3초 초과)"
    im.close()

def t_kakao_trim():
    from editor import trim_to_duration
    frames = [Image.new("RGB", (10, 10)) for _ in range(10)]
    durs = [500] * 10  # 총 5초
    kf, kd = trim_to_duration(frames, durs, 3000)
    assert sum(kd) <= 3000, f"누적 {sum(kd)}ms"
    assert len(kf) == 6, f"프레임수 {len(kf)}"  # 6*500=3000
    for f in frames: f.close()

check("카톡 이모티콘 변환 (360² · WebP · 3초 트림)", t_kakao_basic)
check("trim_to_duration 길이 제한", t_kakao_trim)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
