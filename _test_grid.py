"""
_test_grid.py — 개발자 레벨 위젯 grid 셀 충돌 검출 (xvfb 필요).
같은 부모에서 두 위젯이 같은 (row,column)이면 화면이 겹친다.
- grid_remove() 된 위젯은 grid_info()가 비어 자동 제외.
- CustomTkinter 내부 구조(Canvas 배경 + 내용물이 (0,0)에 함께 배치)는 정상이므로
  Canvas 가 낀 겹침은 오탐으로 보고 제외한다.
"""
import sys
import customtkinter as ctk


def find_collisions(widget, path=""):
    found = []
    bycell = {}
    for child in widget.winfo_children():
        gi = child.grid_info()
        if gi:
            key = (int(gi["row"]), int(gi["column"]))
            bycell.setdefault(key, []).append(child)
    for key, widgets in bycell.items():
        classes = [w.winfo_class() for w in widgets]
        if len(widgets) > 1 and "Canvas" not in classes:  # CTk 내부 Canvas 겹침 제외
            found.append((path or "/", key, classes))
    for child in widget.winfo_children():
        found += find_collisions(child, path + "/" + child.winfo_class())
    return found


root = ctk.CTk()

# ── 자가 테스트: 일부러 같은 칸에 두 프레임 → 검출돼야 함 ──
probe = ctk.CTkFrame(root)
a = ctk.CTkFrame(probe); a.grid(row=0, column=0)
b = ctk.CTkFrame(probe); b.grid(row=0, column=0)  # 의도적 충돌
root.update_idletasks()
selftest = find_collisions(probe)
if not selftest:
    print("  ⚠️ 검출기 자가 테스트 실패 — 충돌을 못 잡음"); root.destroy(); sys.exit(2)
print("  ✅ 검출기 자가 테스트: 의도적 충돌 정상 검출")
probe.destroy()

from ui_merge_tab import MergeTab
from ui_video_tab import VideoTab
from ui_record_tab import RecordTab
from ui_edit_tab import EditTab

total = 0
for name, cls in [("MergeTab", MergeTab), ("VideoTab", VideoTab),
                  ("RecordTab", RecordTab), ("EditTab", EditTab)]:
    frame = ctk.CTkFrame(root)
    inst = cls(frame)
    root.update_idletasks()
    cols = find_collisions(inst)
    if cols:
        total += len(cols)
        print(f"  ❌ {name}: {len(cols)}건 충돌")
        for path, key, classes in cols:
            print(f"       row/col={key} 에 {classes} 겹침  ({path})")
    else:
        print(f"  ✅ {name}: 충돌 없음")
    frame.destroy()

root.destroy()
print(f"\n{'='*40}\n총 충돌: {total}건")
sys.exit(0 if total == 0 else 1)
