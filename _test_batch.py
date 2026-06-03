"""
_test_batch.py — 편집 탭 배치 변환 + 결과 미리보기 검증 (xvfb 필요).
"""
import sys, glob
import customtkinter as ctk
from pathlib import Path
from PIL import Image

OUT = Path("_test_out"); OUT.mkdir(exist_ok=True)
ASSET = Path("_test_assets"); ASSET.mkdir(exist_ok=True)

# 3개의 소스 GIF 생성 (200x200)
from image_merger import MergeJob, merge_images
srcs = []
for k in range(3):
    imgs = []
    for j, c in enumerate(["red", "blue"]):
        p = ASSET / f"b{k}_{j}.png"; Image.new("RGB", (200, 200), c).save(p); imgs.append(str(p))
    job = MergeJob(); job.image_paths = imgs; job.output_format = "gif"
    job.default_delay = 200; job.output_path = str(OUT / f"bsrc{k}.gif")
    merge_images(job); srcs.append(str(OUT / f"bsrc{k}.gif"))

root = ctk.CTk(); frame = ctk.CTkFrame(root)
from ui_edit_tab import EditTab
tab = EditTab(frame); root.update_idletasks()

outdir = str(OUT / "batch"); Path(outdir).mkdir(exist_ok=True)
# 기존 산출물 정리
for f in glob.glob(outdir + "/*"):
    Path(f).unlink()

tab._batch_paths = srcs
tab._output_dir.set(outdir)
tab._format_var.set("webp")     # GIF → WebP 일괄 변환
tab._resize_var.set("50%")      # + 50% 축소
edits = tab._build_edits()
tab._run_batch(srcs, edits, "webp", outdir)  # 동기 실행 (변환은 즉시 일어남)

outs = sorted(glob.glob(outdir + "/*.webp"))  # 파일명에 타임스탬프 붙음
ok = True
def expect(c, m):
    global ok; print(("  ✅ " if c else "  ❌ ") + m); ok = ok and c

expect(len(outs) == 3, f"3개 파일 모두 변환 생성 (실제 {len(outs)}: {[Path(o).name for o in outs]})")
if outs:
    im = Image.open(outs[0])
    expect(im.format == "WEBP", "출력이 WebP 포맷")
    expect(im.size == (100, 100), f"50% 리사이즈 적용됨 (실제 {im.size})")
    im.close()

# 결과 미리보기 버튼 생성 확인
tab._file_path = srcs[0]
tab._show_result_preview(srcs[0])
expect(tab._result_preview_btn is not None, "결과 미리보기 버튼 생성됨")

root.destroy()
print(f"\n{'='*40}\n{'전체 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
