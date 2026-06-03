"""
_test_planner_ui.py — 영상 기획 탭 UI 검증 (xvfb 필요)
"""
import sys
import customtkinter as ctk
from ui_planner_tab import PlannerTab

root = ctk.CTk(); frame = ctk.CTkFrame(root)
tab = PlannerTab(frame); root.update_idletasks()

ok = True
def expect(c, m):
    global ok; print(("  ✅ " if c else "  ❌ ") + m); ok = ok and c

# 입력 채우기
tab._product.insert(0, "블로그 자동화봇")
tab._problem.insert("1.0", "매일 블로그 글 쓸 시간이 없다")
tab._misconception.insert(0, "글쓰기 실력")
tab._hook.set("반전형"); tab._length.set("쇼츠 30초")

# 예시 버튼
tab._fill_problem()
expect(tab._problem.get("1.0", "end-1c").strip() != "", "문제 예시 채우기")

# 다시 우리 문제로
tab._problem.delete("1.0", "end"); tab._problem.insert("1.0", "매일 블로그 글 쓸 시간이 없다")

# 생성
tab._generate()
out = tab._out.get("1.0", "end-1c")
expect("영상 기획서" in out, "기획서 생성됨")
expect("검수 리포트" in out, "검수 리포트 포함")
expect("실력가" not in out, "조사 오류 없음")
expect("블로그 자동화봇" in out, "상품명 반영")

# 직접입력 타겟
tab._target_custom.insert(0, "1인 미디어 운영자")
expect(tab._get_target() == "1인 미디어 운영자", "직접입력 타겟 우선")

# 복사 (클립보드)
tab._copy()
expect(tab.clipboard_get().strip() != "", "복사 동작")

root.destroy()
print(f"\n{'='*40}\n{'전체 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
