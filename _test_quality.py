"""
_test_quality.py — v1.8.0 GIF 화질 프리셋/용량 최적화 검증
─────────────────────────────────────────────────────────
사용법: 이 파일을 'GIF 메이커' 폴더(main.py 있는 곳)에 넣고
        명령창에서  →  python _test_quality.py
(소스로 실행할 때만 됩니다. exe만 있으면 아래 'UI 수동 테스트'를 참고하세요.)
"""

import os
import sys
import tempfile
import subprocess


def _frames(path):
    """GIF 프레임 수 세기"""
    try:
        from PIL import Image
        g = Image.open(path)
        n = 0
        try:
            while True:
                n += 1
                g.seek(g.tell() + 1)
        except EOFError:
            pass
        return n
    except Exception:
        return 0


def main():
    print("=" * 50)
    print(" GIF 메이커 v1.8.0 — 화질 프리셋 검증")
    print("=" * 50)

    try:
        from utils import find_ffmpeg
        from video_converter import ConvertJob, convert_video
        from optimizer import gifsicle_available
    except Exception as e:
        print("❌ 모듈 import 실패 — 'GIF 메이커' 폴더 안에서 실행하세요.")
        print("   ", e)
        return

    ff = find_ffmpeg()
    if not ff:
        print("❌ ffmpeg를 못 찾음 — 폴더에 ffmpeg(.exe)가 있는지 확인하세요.")
        return
    print("✅ ffmpeg :", ff)
    print("✅ gifsicle 번들 :", gifsicle_available(),
          "  (True면 균형/빠른로딩이 더 작아집니다)")

    # 테스트용 2초 영상 생성 (움직임+그라데이션이 있어 화질 차이가 잘 보임)
    tv = tempfile.mktemp(suffix=".mp4")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i",
         "testsrc=size=480x360:rate=30:duration=2", "-pix_fmt", "yuv420p", tv],
        capture_output=True,
    )
    if not os.path.exists(tv):
        print("❌ 테스트 영상 생성 실패")
        return

    print("\n── ① 영상 → GIF, 3개 프리셋 ──")
    results = {}
    for mode, name in (("best", "🟢 최고화질"), ("balanced", "🔵 균형"), ("fast", "🟡 빠른로딩")):
        job = ConvertJob()
        job.input_path = tv
        job.output_format = "gif"
        job.width = 480
        job.fps = 15 if mode == "fast" else 20
        job.quality_mode = mode
        job.gif_lossy = {"best": 0, "balanced": 30, "fast": 60}[mode]
        job.output_path = os.path.join(tempfile.gettempdir(), f"gifqtest_{mode}.gif")
        convert_video(job, on_progress=lambda p, m: None)
        ok = os.path.exists(job.output_path)
        kb = os.path.getsize(job.output_path) // 1024 if ok else -1
        results[mode] = kb
        print(f"  {name} : {'OK ' if ok else '실패'} {kb:>5} KB  {_frames(job.output_path)}프레임")
        print(f"           → {job.output_path}")

    order_ok = results.get("best", 0) >= results.get("balanced", 0) >= results.get("fast", 0)
    print(f"\n  용량 순서(최고화질 ≥ 균형 ≥ 빠른로딩) : {'✅ 정상' if order_ok else '⚠ 확인 필요'}")

    print("\n── ② 이미지 → GIF (프레임 색 깜빡임 제거) ──")
    try:
        from PIL import Image
        from image_merger import _save_gif, MergeJob
        frames = []
        for k in range(5):
            im = Image.new("RGB", (160, 100))
            for x in range(160):
                for y in range(100):
                    im.putpixel((x, y), ((x + k * 40) % 256, (y * 2) % 256, (k * 50) % 256))
            frames.append(im)
        job = MergeJob()
        job.loop = 0
        job.bg_color = "white"
        job.output_path = os.path.join(tempfile.gettempdir(), "gifqtest_merge.gif")
        _save_gif(frames, [120] * 5, job)
        kb = os.path.getsize(job.output_path) // 1024
        print(f"  ✅ 저장 OK : {kb} KB, {_frames(job.output_path)}프레임")
        print(f"           → {job.output_path}")
    except Exception as e:
        print("  ❌ 실패 :", e)

    print("\n" + "=" * 50)
    print(" 끝! 위 경로의 GIF들을 직접 열어 비교해보세요.")
    print("  - 🟢최고화질 vs 🟡빠른로딩 : 화질/용량 차이 확인")
    print("  - merge.gif : 색이 깜빡이지 않고 부드러운지 확인")
    print("=" * 50)


if __name__ == "__main__":
    main()
