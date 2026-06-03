"""
_test_video_ui.py — 영상 탭의 MP4/쇼츠 UI 상호작용 검증 (xvfb 필요).
포맷에 따라 쇼츠 체크박스가 활성/비활성 되는지, job에 shorts 플래그가 실리는지 확인.
"""
import sys
import customtkinter as ctk
from ui_video_tab import VideoTab

root = ctk.CTk()
frame = ctk.CTkFrame(root)
tab = VideoTab(frame)
root.update_idletasks()

ok = True
def expect(cond, msg):
    global ok
    print(("  ✅ " if cond else "  ❌ ") + msg)
    ok = ok and cond

# 1) 기본(gif): 쇼츠 비활성
tab._format_var.set("gif"); tab._on_format_change()
expect(str(tab._shorts_check.cget("state")) == "disabled", "GIF일 때 쇼츠 체크박스 비활성")

# 2) MP4 선택: 쇼츠 활성
tab._format_var.set("mp4"); tab._on_format_change()
expect(str(tab._shorts_check.cget("state")) == "normal", "MP4일 때 쇼츠 체크박스 활성")

# 3) 쇼츠 켠 뒤 job 빌드 → shorts_vertical True
tab._shorts_var.set(True)
tab._video_path = "/tmp/x.mp4"
import types
tab._video_info = types.SimpleNamespace(width=1920, height=1080, duration=10.0, fps=30.0)
job = tab._build_job()
expect(job.output_format == "mp4", "job 포맷 = mp4")
expect(job.shorts_vertical is True, "job.shorts_vertical = True")
expect(job.output_path.endswith(".mp4"), "출력 확장자 .mp4")

# 4) 다시 webp로: 쇼츠 비활성
tab._format_var.set("webp"); tab._on_format_change()
expect(str(tab._shorts_check.cget("state")) == "disabled", "WebP로 돌아가면 쇼츠 비활성")

root.destroy()
print(f"\n{'='*40}\n{'전체 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
