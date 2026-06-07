"""
_test_gui.py — GUI 구성 검증 (xvfb 필요).
전체 앱과 각 탭이 에러 없이 생성/배치되는지 확인. 위젯 grid 충돌 등도 여기서 드러남.
실행: xvfb-run -a .venv/bin/python _test_gui.py
"""
import sys, traceback

results = []
def check(name, fn):
    try:
        fn(); results.append((name, True, "")); print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False, traceback.format_exc())); print(f"  ❌ {name}: {e}")

import customtkinter as ctk

# 각 탭을 하나의 root 안에서 개별 생성
root = ctk.CTk()
root.geometry("1400x900")

def make_tab(cls):
    frame = ctk.CTkFrame(root)
    inst = cls(frame)
    root.update_idletasks()
    return inst

def t_merge():
    from ui_merge_tab import MergeTab
    make_tab(MergeTab)
check("MergeTab 생성", t_merge)

def t_video():
    from ui_video_tab import VideoTab
    make_tab(VideoTab)
check("VideoTab 생성", t_video)

def t_record():
    from ui_record_tab import RecordTab
    make_tab(RecordTab)
check("RecordTab 생성", t_record)

def t_edit():
    from ui_edit_tab import EditTab
    make_tab(EditTab)
check("EditTab 생성", t_edit)

root.destroy()

# 전체 앱 생성 (실제 경로)
def t_app():
    from ui_app import GifMakerApp
    app = GifMakerApp()
    app.update_idletasks()
    assert len(app._tab_instances) == 4, f"탭 개수 {len(app._tab_instances)}"
    app.destroy()
check("전체 앱(GifMakerApp) 생성 + 4탭", t_app)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n{'='*40}\n결과: {passed}/{total} 통과")
for name, ok, tb in results:
    if not ok:
        print(f"\n❌ {name}\n{tb}")
sys.exit(0 if passed == total else 1)
