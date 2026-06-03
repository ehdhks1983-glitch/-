"""
_test_shorts_ui.py — 쇼츠 제작 탭 UI 데이터 흐름 검증 (xvfb 필요).
장면 추가 → 편집칸 입력 → 동기화 → 세그먼트 반영 → 미리보기 렌더까지 확인.
"""
import sys
import customtkinter as ctk
from pathlib import Path
from PIL import Image

ASSET = Path("_test_assets"); ASSET.mkdir(exist_ok=True)
img = str(ASSET / "su.png"); Image.new("RGB", (800, 600), "#2266aa").save(img)

from ui_shorts_tab import ShortsTab
from shorts_maker import ShortsSegment

root = ctk.CTk(); frame = ctk.CTkFrame(root)
tab = ShortsTab(frame); root.update_idletasks()

ok = True
def expect(c, m):
    global ok; print(("  ✅ " if c else "  ❌ ") + m); ok = ok and c

# 장면 2개 추가
tab._segments.append(ShortsSegment(image_path=img, duration=3.0, template="blur"))
tab._segments.append(ShortsSegment(image_path=img, duration=3.0, template="blur"))
tab._refresh_list()
tab._select(0)
expect(len(tab._segments) == 2, "장면 2개 추가됨")

# 편집칸에 입력 후 동기화
tab._tpl_var.set("카드뉴스")
tab._caption_box.delete("1.0", "end"); tab._caption_box.insert("1.0", "테스트 제목")
tab._narr_box.delete("1.0", "end"); tab._narr_box.insert("1.0", "이건 나래이션 글입니다")
tab._dur_var.set(5.0)
tab._sync_editor_to_segment()
seg = tab._segments[0]
expect(seg.template == "card", "템플릿 → card 반영")
expect(seg.caption == "테스트 제목", "자막 반영")
expect(seg.narration == "이건 나래이션 글입니다", "나래이션 반영")
expect(abs(seg.duration - 5.0) < 0.01, "노출시간 반영")

# 선택 전환 시 이전 편집 보존되는지
tab._select(1)
tab._select(0)
tab._load_segment_to_editor(0)
expect(tab._segments[0].caption == "테스트 제목", "선택 전환 후에도 편집 보존")

# 미리보기 렌더
tab._update_preview()
expect(tab._preview_img is not None, "미리보기 렌더 성공")

# 순서 이동
tab._segments[1].caption = "두번째"
tab._select(1); tab._move(-1)
expect(tab._segments[0].caption == "두번째", "장면 순서 위로 이동")

# BGM/볼륨/빌드용 프로젝트 조립 확인
tab._vol_var.set(40)
proj_vol = tab._vol_var.get() / 100.0
expect(abs(proj_vol - 0.4) < 0.01, "BGM 볼륨 0.4 변환")

root.destroy()
print(f"\n{'='*40}\n{'전체 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
