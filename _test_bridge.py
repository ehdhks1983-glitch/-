"""
_test_bridge.py — 기획 → 쇼츠 연결 통합 검증 (xvfb 필요).
전체 앱을 띄워, 기획 생성 → '쇼츠로 보내기' → 쇼츠 탭에 장면이 채워지는지 확인.
"""
import sys
import customtkinter as ctk
from ui_app import GifMakerApp

app = GifMakerApp()
app.update_idletasks()

ok = True
def expect(c, m):
    global ok; print(("  ✅ " if c else "  ❌ ") + m); ok = ok and c

# 탭 순서: 기획 다음 쇼츠
names = list(app._tab_instances.keys())
expect(names[0].startswith("📝") and names[1].startswith("📱"),
       f"탭 순서: 기획 → 쇼츠 (실제: {names[0]} → {names[1]})")
expect(app._tabview.get().startswith("📝"), "기본 탭 = 영상 기획")

# 기획 입력 + 생성
pl = app._planner_tab
pl._product.insert(0, "블로그 자동화봇")
pl._problem.insert("1.0", "매일 블로그 글 쓸 시간이 없다")
pl._misconception.insert(0, "글쓰기 실력")
pl._generate()
expect(pl._last_plan is not None, "기획서 생성됨")
n = len(pl._last_plan["structure"])

# 쇼츠로 보내기
pl._send_to_shorts()
sh = app._shorts_tab
expect(len(sh._segments) == n, f"쇼츠에 장면 {n}개 전달 (실제 {len(sh._segments)})")
expect(bool(sh._segments[0].narration), "1번 장면 나래이션 채워짐")
expect(bool(sh._segments[0].caption), "1번 장면 자막 채워짐")
expect(sh._segments[0].image_path == "", "사진은 비어있음(사용자가 추가)")
expect(app._tabview.get().startswith("📱"), "쇼츠 탭으로 자동 전환됨")

# 쇼츠에서 미리보기/빌드 데이터 정합성 (사진 없이도 장면 렌더 가능해야)
sh._select(0)
expect(sh._preview_img is not None, "전달된 장면 미리보기 렌더")

app.destroy()
print(f"\n{'='*40}\n{'전체 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
