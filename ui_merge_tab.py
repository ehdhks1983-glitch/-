"""
ui_merge_tab.py - 이미지 합치기 탭 UI
드래그앤드롭, 순서변경, 미리보기, 설정 패널
"""

import os
import threading
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from config import settings
from utils import (
    is_image_file, get_image_info, format_filesize,
    generate_output_name, IMAGE_EXTS,
)
from image_merger import MergeJob, merge_images, estimate_output_size
from optimizer import auto_optimize


class ImageListItem(ctk.CTkFrame):
    """이미지 리스트 개별 아이템 (썸네일 + 이름 + 삭제)"""

    def __init__(self, master, path: str, index: int,
                 thumb=None, info=None, selected=False,
                 on_delete=None, on_select=None):
        bg = "#1e3a5f" if selected else "gray20"
        super().__init__(master, fg_color=bg, corner_radius=6, height=50)
        self.path = path
        self.index = index
        self._on_delete = on_delete
        self._on_select = on_select
        self._thumb_ref = thumb  # 외부에서 캐시된 썸네일 받기

        self.pack_propagate(False)
        self.configure(height=50)

        # 썸네일
        if self._thumb_ref:
            thumb_label = ctk.CTkLabel(self, image=self._thumb_ref, text="")
            thumb_label.pack(side="left", padx=(8, 4), pady=4)
        else:
            idx_label = ctk.CTkLabel(self, text=f"#{index+1}", width=40,
                                     font=ctk.CTkFont(size=12))
            idx_label.pack(side="left", padx=(8, 4))

        # 파일명 + 정보
        name = Path(path).name
        if len(name) > 25:
            name = name[:22] + "..."
        size_str = ""
        if info:
            w, h, fmt = info
            size_str = f"  ({w}x{h})"

        name_label = ctk.CTkLabel(
            self, text=f"{name}{size_str}",
            font=ctk.CTkFont(size=12), anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True, padx=4)

        # 삭제 버튼
        del_btn = ctk.CTkButton(
            self, text="✕", width=30, height=30,
            fg_color="gray30", hover_color="#cc4444",
            font=ctk.CTkFont(size=14),
            command=lambda: self._on_delete(self.index) if self._on_delete else None,
        )
        del_btn.pack(side="right", padx=8, pady=4)

        # 클릭 이벤트
        self.bind("<Button-1>", lambda e: self._on_select(self.index) if self._on_select else None)
        name_label.bind("<Button-1>", lambda e: self._on_select(self.index) if self._on_select else None)


class MergeTab(ctk.CTkFrame):
    """이미지 합치기 탭 전체 UI"""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._image_paths: List[str] = []
        self._preview_frames: List[ImageTk.PhotoImage] = []
        self._preview_index: int = 0
        self._preview_playing: bool = False
        self._preview_after_id = None
        self._preview_current_index: int = 0  # 자막 미리보기 갱신 시 현재 표시 중인 프레임 인덱스
        self._job: Optional[MergeJob] = None
        self._working: bool = False
        self._selected_index: Optional[int] = None
        self._list_items: list = []  # ImageListItem 참조

        # 성능 캐시 (경로 → 데이터)
        self._thumb_cache: dict = {}       # path → ImageTk.PhotoImage (40x40)
        self._mini_thumb_cache: dict = {}  # path → ImageTk.PhotoImage (60x48, 타임라인용)
        self._info_cache: dict = {}        # path → (w, h, fmt)

        self._build_ui()

    # ════════════════════════════════════════
    # 썸네일/정보 캐시
    # ════════════════════════════════════════
    def _get_thumb(self, path: str) -> Optional[ImageTk.PhotoImage]:
        """40x40 리스트용 썸네일 (캐시됨)"""
        if path in self._thumb_cache:
            return self._thumb_cache[path]
        try:
            img = Image.open(path)
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            img.thumbnail((40, 40))
            photo = ImageTk.PhotoImage(img)
            img.close()
            self._thumb_cache[path] = photo
            return photo
        except Exception:
            return None

    def _get_mini_thumb(self, path: str) -> Optional[ImageTk.PhotoImage]:
        """60x48 타임라인용 미니 썸네일 (캐시됨)"""
        if path in self._mini_thumb_cache:
            return self._mini_thumb_cache[path]
        try:
            img = Image.open(path)
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            img.thumbnail((60, 48))
            photo = ImageTk.PhotoImage(img)
            img.close()
            self._mini_thumb_cache[path] = photo
            return photo
        except Exception:
            return None

    def _get_info(self, path: str) -> Optional[tuple]:
        """이미지 정보 (캐시됨)"""
        if path in self._info_cache:
            return self._info_cache[path]
        info = get_image_info(path)
        if info:
            self._info_cache[path] = info
        return info

    def _clear_caches(self):
        """캐시 전체 클리어"""
        self._thumb_cache.clear()
        self._mini_thumb_cache.clear()
        self._info_cache.clear()

    def _build_ui(self):
        # ─── 3-Column 레이아웃 ───
        self.grid_columnconfigure(0, weight=1, minsize=260)   # 좌: 이미지 리스트
        self.grid_columnconfigure(1, weight=2, minsize=400)   # 중: 미리보기
        self.grid_columnconfigure(2, weight=1, minsize=260)   # 우: 설정
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    # ════════════════════════════════════════
    # 좌측: 이미지 리스트
    # ════════════════════════════════════════
    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color="gray14", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # 헤더
        header = ctk.CTkFrame(left, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(header, text="🖼️ 이미지 목록",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")

        ctk.CTkButton(btn_frame, text="➕ 추가", width=70, height=28,
                      font=ctk.CTkFont(size=12),
                      command=self._add_images).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="🗑 전체삭제", width=80, height=28,
                      font=ctk.CTkFont(size=12),
                      fg_color="gray30", hover_color="#cc4444",
                      command=self._clear_images).pack(side="left", padx=2)

        # 이미지 리스트 (스크롤)
        self._list_scroll = ctk.CTkScrollableFrame(
            left, fg_color="gray17", corner_radius=6,
        )
        self._list_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        # 드래그앤드롭 안내
        self._drop_label = ctk.CTkLabel(
            self._list_scroll,
            text="이미지를 여기에\n드래그 앤 드롭\n\n또는 [➕ 추가] 클릭",
            font=ctk.CTkFont(size=13),
            text_color="gray50",
        )
        self._drop_label.pack(expand=True, pady=60)

        # 순서 변경 버튼
        order_frame = ctk.CTkFrame(left, fg_color="transparent")
        order_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))

        ctk.CTkButton(order_frame, text="🔼 위로", width=70, height=28,
                      font=ctk.CTkFont(size=12), fg_color="gray30",
                      command=lambda: self._move_selected(-1)).pack(side="left", padx=2)
        ctk.CTkButton(order_frame, text="🔽 아래로", width=70, height=28,
                      font=ctk.CTkFont(size=12), fg_color="gray30",
                      command=lambda: self._move_selected(1)).pack(side="left", padx=2)

        self._count_label = ctk.CTkLabel(
            order_frame, text="0장", font=ctk.CTkFont(size=12), text_color="gray50"
        )
        self._count_label.pack(side="right", padx=8)

    # ════════════════════════════════════════
    # 중앙: 미리보기
    # ════════════════════════════════════════
    def _build_center_panel(self):
        center = ctk.CTkFrame(self, fg_color="gray14", corner_radius=10)
        center.grid(row=0, column=1, sticky="nsew", padx=4, pady=0)
        center.grid_rowconfigure(0, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # ★ 미리보기 고정 크기 컨테이너 (이미지 크기와 무관하게 크기 고정)
        #   → 이미지 사이즈가 달라져도 좌우 패널이 흔들리지 않음
        preview_container = ctk.CTkFrame(center, fg_color="transparent")
        preview_container.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        preview_container.grid_propagate(False)  # 자식 위젯에 따라 컨테이너 크기 변경 차단
        preview_container.grid_rowconfigure(0, weight=1)
        preview_container.grid_columnconfigure(0, weight=1)

        # 미리보기 캔버스
        self._preview_label = ctk.CTkLabel(
            preview_container, text="미리보기",
            font=ctk.CTkFont(size=16),
            text_color="gray40",
        )
        self._preview_label.grid(row=0, column=0, sticky="nsew")

        # 컨트롤 바
        ctrl = ctk.CTkFrame(center, fg_color="transparent", height=40)
        ctrl.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        self._play_btn = ctk.CTkButton(
            ctrl, text="▶ 재생", width=80, height=30,
            font=ctk.CTkFont(size=12),
            command=self._toggle_preview,
        )
        self._play_btn.pack(side="left", padx=4)

        self._frame_label = ctk.CTkLabel(
            ctrl, text="0/0", font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._frame_label.pack(side="left", padx=8)

        self._size_est_label = ctk.CTkLabel(
            ctrl, text="예상 용량: -",
            font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._size_est_label.pack(side="right", padx=8)

        # ── 타임라인 (개별 프레임 딜레이) ──
        tl_header = ctk.CTkFrame(center, fg_color="transparent", height=24)
        tl_header.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))

        ctk.CTkLabel(
            tl_header, text="🎬 타임라인 (프레임별 딜레이 ms)",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        self._tl_reset_btn = ctk.CTkButton(
            tl_header, text="일괄 초기화", width=80, height=22,
            font=ctk.CTkFont(size=11), fg_color="gray30",
            command=self._reset_all_delays,
        )
        self._tl_reset_btn.pack(side="right")

        self._timeline_scroll = ctk.CTkScrollableFrame(
            center, fg_color="gray17", corner_radius=6,
            height=100, orientation="horizontal",
        )
        self._timeline_scroll.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 8))
        self._timeline_items: list = []  # (frame, entry, thumb_ref) 리스트
        self._frame_delays_map: dict = {}  # index → delay ms (0이면 기본값)

    # ════════════════════════════════════════
    # 우측: 설정 패널
    # ════════════════════════════════════════
    def _build_right_panel(self):
        right = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10)
        right.grid(row=0, column=2, sticky="nsew", padx=(4, 0), pady=0)

        pad = {"padx": 12, "pady": (4, 2), "sticky": "ew"}

        # ── 출력 포맷 ──
        ctk.CTkLabel(right, text="📦 출력 포맷",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, **pad)

        self._format_var = ctk.StringVar(value=settings.get("merge_output_format"))
        fmt_frame = ctk.CTkFrame(right, fg_color="transparent")
        fmt_frame.grid(row=1, column=0, **pad)
        for i, (text, val) in enumerate([("GIF", "gif"), ("WebP", "webp"), ("APNG", "apng")]):
            ctk.CTkRadioButton(
                fmt_frame, text=text, variable=self._format_var, value=val,
                font=ctk.CTkFont(size=12),
                command=self._on_settings_change,
            ).grid(row=0, column=i, padx=8)

        # ── 속도 / FPS ──
        ctk.CTkLabel(right, text="⏱️ 프레임 딜레이 (ms)",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=2, column=0, **pad)

        delay_frame = ctk.CTkFrame(right, fg_color="transparent")
        delay_frame.grid(row=3, column=0, **pad)

        self._delay_var = ctk.IntVar(value=settings.get("merge_delay_ms"))
        self._delay_slider = ctk.CTkSlider(
            delay_frame, from_=20, to=1000,
            variable=self._delay_var,
            command=self._on_delay_change,
            width=160,
        )
        self._delay_slider.pack(side="left", padx=(0, 8))

        self._delay_entry = ctk.CTkEntry(delay_frame, width=60, height=28,
                                          font=ctk.CTkFont(size=12))
        self._delay_entry.insert(0, str(self._delay_var.get()))
        self._delay_entry.pack(side="left")
        self._delay_entry.bind("<Return>", self._on_delay_entry)

        self._fps_label = ctk.CTkLabel(
            right, text=f"≈ {1000 // max(1, self._delay_var.get())} FPS",
            font=ctk.CTkFont(size=11), text_color="gray50",
        )
        self._fps_label.grid(row=4, column=0, padx=12, pady=(0, 4), sticky="w")

        # ── 반복 ──
        ctk.CTkLabel(right, text="🔁 반복 횟수",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=5, column=0, **pad)

        self._loop_var = ctk.StringVar(value="무한 반복")
        self._loop_menu = ctk.CTkOptionMenu(
            right, values=["무한 반복", "1회", "2회", "3회", "5회"],
            variable=self._loop_var,
            font=ctk.CTkFont(size=12),
            command=self._on_settings_change,
        )
        self._loop_menu.grid(row=6, column=0, **pad)

        # ── 크기 조절 ──
        ctk.CTkLabel(right, text="📐 크기 조절",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=7, column=0, **pad)

        self._resize_var = ctk.StringVar(value="SNS 최적 (640px)")
        self._resize_menu = ctk.CTkOptionMenu(
            right,
            values=["SNS 최적 (640px)", "고화질 (1080px)", "가장 큰 이미지 기준",
                    "가장 작은 이미지 기준", "커스텀 크기", "원본 유지"],
            variable=self._resize_var,
            font=ctk.CTkFont(size=12),
            command=self._on_resize_change,
        )
        self._resize_menu.grid(row=8, column=0, **pad)

        # 커스텀 크기 입력 (기본 숨김)
        self._custom_size_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._custom_size_frame.grid(row=9, column=0, **pad)
        self._custom_size_frame.grid_remove()

        ctk.CTkLabel(self._custom_size_frame, text="W:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._cw_entry = ctk.CTkEntry(self._custom_size_frame, width=60, height=28)
        self._cw_entry.insert(0, "800")
        self._cw_entry.pack(side="left", padx=4)
        ctk.CTkLabel(self._custom_size_frame, text="H:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 0))
        self._ch_entry = ctk.CTkEntry(self._custom_size_frame, width=60, height=28)
        self._ch_entry.insert(0, "600")
        self._ch_entry.pack(side="left", padx=4)

        # ── 배경색 ──
        ctk.CTkLabel(right, text="🎨 배경색",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=10, column=0, **pad)

        self._bg_var = ctk.StringVar(value="검정 (#000000)")
        self._bg_menu = ctk.CTkOptionMenu(
            right,
            values=["검정 (#000000)", "흰색 (#FFFFFF)", "투명 (WebP/APNG만)"],
            variable=self._bg_var,
            font=ctk.CTkFont(size=12),
        )
        self._bg_menu.grid(row=11, column=0, **pad)

        # ── 품질 (WebP) ──
        ctk.CTkLabel(right, text="💎 품질 (WebP)",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=12, column=0, **pad)

        self._quality_var = ctk.IntVar(value=settings.get("merge_quality"))
        quality_frame = ctk.CTkFrame(right, fg_color="transparent")
        quality_frame.grid(row=13, column=0, **pad)

        self._quality_slider = ctk.CTkSlider(
            quality_frame, from_=10, to=100,
            variable=self._quality_var,
            command=self._on_settings_change,
            width=160,
        )
        self._quality_slider.pack(side="left", padx=(0, 8))
        self._quality_label = ctk.CTkLabel(
            quality_frame, text=f"{self._quality_var.get()}%",
            font=ctk.CTkFont(size=12),
        )
        self._quality_label.pack(side="left")

        # ── GIF 용량 줄이기 ──
        ctk.CTkLabel(right, text="📦 GIF 용량 줄이기",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=14, column=0, **pad)

        opt_frame = ctk.CTkFrame(right, fg_color="transparent")
        opt_frame.grid(row=15, column=0, **pad)

        self._optimize_var = ctk.BooleanVar(value=False)
        self._optimize_check = ctk.CTkCheckBox(
            opt_frame, text="완성 파일이 크면 자동 압축",
            variable=self._optimize_var,
            font=ctk.CTkFont(size=12),
            command=self._on_optimize_toggle,
        )
        self._optimize_check.pack(side="left")

        self._target_size_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._target_size_frame.grid(row=16, column=0, **pad)
        self._target_size_frame.grid_remove()

        ctk.CTkLabel(self._target_size_frame, text="목표:",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._target_kb_entry = ctk.CTkEntry(
            self._target_size_frame, width=70, height=28,
            font=ctk.CTkFont(size=12),
        )
        self._target_kb_entry.insert(0, "5000")
        self._target_kb_entry.pack(side="left", padx=4)
        ctk.CTkLabel(self._target_size_frame, text="KB",
                     font=ctk.CTkFont(size=12), text_color="gray50").pack(side="left")

        # ══════════════════════════════════════════
        # 💬 자막 (선택) — 영상 탭과 동일한 UI
        # ══════════════════════════════════════════
        ctk.CTkLabel(right, text="💬 자막 (선택)",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=15, column=0, **pad)

        sub_container = ctk.CTkFrame(right, fg_color="gray20", corner_radius=8)
        sub_container.grid(row=16, column=0, padx=12, pady=(2, 4), sticky="ew")

        # 텍스트 입력
        sub_text_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_text_frame.pack(fill="x", padx=8, pady=(8, 4))

        self._sub_entry = ctk.CTkTextbox(
            sub_text_frame, font=ctk.CTkFont(size=12), height=50,
            wrap="word",
        )
        self._sub_entry.pack(fill="x")

        ctk.CTkLabel(
            sub_text_frame, text="💡 Enter로 줄바꿈 가능",
            font=ctk.CTkFont(size=9), text_color="gray50", anchor="w",
        ).pack(anchor="w")

        # 위치
        sub_pos_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_pos_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkLabel(sub_pos_frame, text="위치",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._sub_pos_var = ctk.StringVar(value="하단")
        ctk.CTkOptionMenu(
            sub_pos_frame, values=["하단", "중앙", "상단"],
            variable=self._sub_pos_var, width=80, height=24,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=2)

        # 크기 + 굵기
        sub_style_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_style_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkLabel(sub_style_frame, text="크기",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self._sub_size_var = ctk.IntVar(value=32)
        ctk.CTkSlider(
            sub_style_frame, from_=16, to=72,
            variable=self._sub_size_var, width=100, height=16,
        ).pack(side="left", padx=2)
        self._sub_size_label = ctk.CTkLabel(
            sub_style_frame, text="32",
            font=ctk.CTkFont(size=11), width=25,
        )
        self._sub_size_label.pack(side="left", padx=(0, 8))
        self._sub_size_var.trace_add("write", lambda *_: self._sub_size_label.configure(
            text=str(self._sub_size_var.get())))

        self._sub_bold_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            sub_style_frame, text="굵게",
            variable=self._sub_bold_var,
            font=ctk.CTkFont(size=11),
            width=50, height=20,
        ).pack(side="left", padx=4)

        # 색상
        sub_color_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_color_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkLabel(sub_color_frame, text="색상",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._sub_color_var = ctk.StringVar(value="⬜ 흰색")
        ctk.CTkOptionMenu(
            sub_color_frame,
            values=["⬜ 흰색", "🟨 노랑", "🟥 빨강", "🟩 초록", "🟦 파랑", "⬛ 검정"],
            variable=self._sub_color_var,
            width=110, height=24,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=2)

        # 색상 미리보기 (실시간)
        self._sub_color_preview = ctk.CTkLabel(
            sub_color_frame, text="  Aa  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="gray30", corner_radius=4,
            width=40, height=22,
        )
        self._sub_color_preview.pack(side="left", padx=4)
        self._sub_color_var.trace_add("write", lambda *_: self._update_sub_color_preview())

        # 버튼
        sub_btn_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_btn_frame.pack(fill="x", padx=8, pady=(2, 8))

        ctk.CTkButton(
            sub_btn_frame, text="+ 자막 추가", height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#059669", hover_color="#047857",
            command=self._add_subtitle,
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        ctk.CTkButton(
            sub_btn_frame, text="🗑 전체삭제", height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#4b5563", hover_color="#374151",
            command=self._clear_subtitles,
        ).pack(side="left", padx=(2, 0))

        # 자막 목록
        self._sub_list_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        self._sub_list_frame.pack(fill="x", padx=8, pady=(0, 8))

        self._sub_empty_label = ctk.CTkLabel(
            self._sub_list_frame, text="(자막 없음)",
            font=ctk.CTkFont(size=11), text_color="gray50",
            anchor="w",
        )
        self._sub_empty_label.pack(fill="x")

        self._subtitles_data: list = []  # [{text, position, size, color, bold}, ...]

        # ── 출력 폴더 ──
        ctk.CTkLabel(right, text="📂 출력 폴더",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=17, column=0, **pad)

        out_frame = ctk.CTkFrame(right, fg_color="transparent")
        out_frame.grid(row=18, column=0, **pad)

        self._output_dir = ctk.StringVar(value=settings.get("output_dir"))
        self._out_entry = ctk.CTkEntry(
            out_frame, textvariable=self._output_dir,
            font=ctk.CTkFont(size=11), height=28,
        )
        self._out_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            out_frame, text="📁", width=30, height=28,
            command=self._browse_output,
        ).pack(side="right")

        # ════════════════════════════════════════
        # 하단: 변환 버튼 + 진행률
        # ════════════════════════════════════════
        spacer = ctk.CTkFrame(right, fg_color="transparent", height=16)
        spacer.grid(row=19, column=0)

        self._convert_btn = ctk.CTkButton(
            right, text="🚀 변환 시작", height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._start_convert,
        )
        self._convert_btn.grid(row=20, column=0, padx=12, pady=8, sticky="ew")

        self._cancel_btn = ctk.CTkButton(
            right, text="⏹ 취소", height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#dc2626", hover_color="#b91c1c",
            command=self._cancel_convert,
        )
        self._cancel_btn.grid(row=21, column=0, padx=12, pady=(0, 4), sticky="ew")
        self._cancel_btn.grid_remove()

        self._progress = ctk.CTkProgressBar(right, height=14)
        self._progress.grid(row=22, column=0, padx=12, pady=4, sticky="ew")
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(
            right, text="이미지를 추가하세요",
            font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._status_label.grid(row=23, column=0, padx=12, pady=(0, 8), sticky="w")

    # ════════════════════════════════════════
    # 이미지 관리
    # ════════════════════════════════════════
    def _add_images(self):
        from tkinter import filedialog
        filetypes = [
            ("이미지 파일", " ".join(f"*{e}" for e in IMAGE_EXTS)),
            ("모든 파일", "*.*"),
        ]
        last_dir = settings.get("last_input_dir") or ""
        files = filedialog.askopenfilenames(
            title="이미지 선택",
            filetypes=filetypes,
            initialdir=last_dir if last_dir else None,
        )
        if files:
            settings.set("last_input_dir", str(Path(files[0]).parent))
            settings.save()
            for f in files:
                if is_image_file(f) and f not in self._image_paths:
                    self._image_paths.append(f)
            self._refresh_list()

    def add_files_from_drop(self, paths: List[str]):
        """외부 드래그앤드롭 핸들러"""
        for p in paths:
            p_path = Path(p)
            if p_path.is_dir():
                for child in sorted(p_path.iterdir()):
                    if is_image_file(str(child)) and str(child) not in self._image_paths:
                        self._image_paths.append(str(child))
            elif is_image_file(p) and p not in self._image_paths:
                self._image_paths.append(p)
        self._refresh_list()

    def _clear_images(self):
        self._image_paths.clear()
        self._frame_delays_map.clear()
        self._clear_caches()
        self._stop_preview()
        self._refresh_list()

    def _delete_image(self, index: int):
        if 0 <= index < len(self._image_paths):
            self._image_paths.pop(index)
            # 딜레이 인덱스 리매핑: 삭제된 index 제거 후 뒤쪽 전부 -1
            new_map = {}
            for k, v in self._frame_delays_map.items():
                if k < index:
                    new_map[k] = v
                elif k > index:
                    new_map[k - 1] = v
                # k == index → 삭제
            self._frame_delays_map = new_map
            self._refresh_list()

    def _move_selected(self, direction: int):
        """선택된 아이템 위/아래 이동 + 딜레이도 함께 이동"""
        if not hasattr(self, '_selected_index') or self._selected_index is None:
            return
        idx = self._selected_index
        new_idx = idx + direction
        if 0 <= new_idx < len(self._image_paths):
            # 이미지 순서 스왑
            self._image_paths[idx], self._image_paths[new_idx] = \
                self._image_paths[new_idx], self._image_paths[idx]
            # 딜레이도 스왑
            d_old = self._frame_delays_map.get(idx, 0)
            d_new = self._frame_delays_map.get(new_idx, 0)
            if d_old:
                self._frame_delays_map[new_idx] = d_old
            else:
                self._frame_delays_map.pop(new_idx, None)
            if d_new:
                self._frame_delays_map[idx] = d_new
            else:
                self._frame_delays_map.pop(idx, None)
            self._selected_index = new_idx
            self._refresh_list()

    def _on_select_item(self, index: int):
        self._selected_index = index
        self._show_preview_frame(index)
        self._update_highlight()  # 경량 — 타임라인 리빌드 없이 배경색만 변경

    def _update_highlight(self):
        """리스트 아이템 배경색만 갱신 (위젯 재생성 안 함)"""
        for item in self._list_items:
            if item.index == self._selected_index:
                item.configure(fg_color="#1e3a5f")
            else:
                item.configure(fg_color="gray20")

    def _refresh_list(self):
        """리스트 UI 갱신"""
        for widget in self._list_scroll.winfo_children():
            widget.destroy()
        self._list_items = []

        if not self._image_paths:
            self._drop_label = ctk.CTkLabel(
                self._list_scroll,
                text="이미지를 여기에\n드래그 앤 드롭\n\n또는 [➕ 추가] 클릭",
                font=ctk.CTkFont(size=13),
                text_color="gray50",
            )
            self._drop_label.pack(expand=True, pady=60)
            self._count_label.configure(text="0장")
            self._frame_label.configure(text="0/0")
            self._preview_label.configure(image=None, text="미리보기")
            return

        for i, path in enumerate(self._image_paths):
            is_sel = self._selected_index == i
            item = ImageListItem(
                self._list_scroll, path, i,
                thumb=self._get_thumb(path),
                info=self._get_info(path),
                selected=is_sel,
                on_delete=self._delete_image,
                on_select=self._on_select_item,
            )
            item.pack(fill="x", pady=2, padx=2)
            self._list_items.append(item)

        self._count_label.configure(text=f"{len(self._image_paths)}장")
        self._update_size_estimate()
        self._refresh_timeline()

        # ── ⚠️ 큰 이미지 경고 ──
        self._check_large_images()

        # 첫 프레임 미리보기
        if self._image_paths:
            self._show_preview_frame(0)

    def _show_preview_frame(self, index: int):
        """단일 프레임 미리보기"""
        if not self._image_paths or index >= len(self._image_paths):
            return
        try:
            img = Image.open(self._image_paths[index])
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            # 미리보기 영역에 맞게 리사이즈
            max_w, max_h = 500, 400
            img.thumbnail((max_w, max_h), Image.LANCZOS)

            # ✏️ 자막 미리보기 합성 (있을 때만)
            img = self._draw_subtitles_on_preview(img)

            photo = ImageTk.PhotoImage(img)
            self._preview_label.configure(image=photo, text="")
            self._preview_label._photo = photo  # GC 방지
            img.close()
            self._frame_label.configure(text=f"{index+1}/{len(self._image_paths)}")
            self._preview_current_index = index  # 자막 갱신 시 재호출용
        except Exception:
            self._preview_label.configure(image=None, text="미리보기 실패")

    # ════════════════════════════════════════
    # 타임라인 (개별 프레임 딜레이)
    # ════════════════════════════════════════
    def _refresh_timeline(self):
        """타임라인 UI 갱신 — 프레임별 미니 썸네일 + 딜레이 입력"""
        for w in self._timeline_scroll.winfo_children():
            w.destroy()
        self._timeline_items.clear()

        if not self._image_paths:
            return

        for i, path in enumerate(self._image_paths):
            frame = ctk.CTkFrame(self._timeline_scroll, fg_color="gray25",
                                 corner_radius=6, width=72, height=88)
            frame.pack(side="left", padx=3, pady=2)
            frame.pack_propagate(False)

            # 미니 썸네일 (캐시 사용)
            thumb_ref = self._get_mini_thumb(path)
            if thumb_ref:
                ctk.CTkLabel(frame, image=thumb_ref, text="").pack(pady=(4, 2))
            else:
                ctk.CTkLabel(frame, text=f"#{i+1}", font=ctk.CTkFont(size=10),
                             text_color="gray50").pack(pady=(4, 2))

            # 딜레이 입력
            entry = ctk.CTkEntry(frame, width=56, height=20,
                                 font=ctk.CTkFont(size=10),
                                 placeholder_text="기본",
                                 justify="center")
            entry.pack(pady=(0, 4))

            # 기존 값 복원
            saved = self._frame_delays_map.get(i, 0)
            if saved > 0:
                entry.insert(0, str(saved))

            # 입력 시 저장
            _idx = i  # 클로저 캡처
            entry.bind("<FocusOut>", lambda e, idx=_idx: self._on_timeline_delay(idx))
            entry.bind("<Return>", lambda e, idx=_idx: self._on_timeline_delay(idx))

            # 클릭 시 미리보기
            frame.bind("<Button-1>", lambda e, idx=_idx: self._show_preview_frame(idx))

            self._timeline_items.append((frame, entry, thumb_ref))

    def _on_timeline_delay(self, index: int):
        """타임라인 딜레이 입력 처리"""
        if index >= len(self._timeline_items):
            return
        _, entry, _ = self._timeline_items[index]
        text = entry.get().strip()
        if not text:
            self._frame_delays_map.pop(index, None)
            return
        try:
            val = max(10, min(5000, int(text)))
            self._frame_delays_map[index] = val
            entry.delete(0, "end")
            entry.insert(0, str(val))
        except ValueError:
            entry.delete(0, "end")
            self._frame_delays_map.pop(index, None)

    def _reset_all_delays(self):
        """모든 개별 딜레이를 글로벌 값으로 초기화"""
        self._frame_delays_map.clear()
        for _, entry, _ in self._timeline_items:
            entry.delete(0, "end")

    # ════════════════════════════════════════
    # 미리보기 재생
    # ════════════════════════════════════════
    def _toggle_preview(self):
        if self._preview_playing:
            self._stop_preview()
        else:
            self._start_preview()

    def _start_preview(self):
        if not self._image_paths:
            return
        self._preview_playing = True
        self._preview_index = 0
        self._play_btn.configure(text="⏸ 정지")
        self._play_next_frame()

    def _stop_preview(self):
        self._preview_playing = False
        self._play_btn.configure(text="▶ 재생")
        if self._preview_after_id:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def _play_next_frame(self):
        if not self._preview_playing or not self._image_paths:
            return
        idx = self._preview_index
        self._show_preview_frame(idx)
        self._preview_index = (idx + 1) % len(self._image_paths)
        # 개별 딜레이 우선, 없으면 글로벌 딜레이
        delay = self._frame_delays_map.get(idx, 0) or self._delay_var.get()
        self._preview_after_id = self.after(delay, self._play_next_frame)

    # ════════════════════════════════════════
    # 설정 콜백
    # ════════════════════════════════════════
    def _on_delay_change(self, val=None):
        delay = int(self._delay_var.get())
        self._delay_entry.delete(0, "end")
        self._delay_entry.insert(0, str(delay))
        fps = 1000 // max(1, delay)
        self._fps_label.configure(text=f"≈ {fps} FPS")
        self._update_size_estimate()

    def _on_delay_entry(self, event=None):
        try:
            val = int(self._delay_entry.get())
            val = max(20, min(2000, val))
            self._delay_var.set(val)
            self._on_delay_change()
        except ValueError:
            pass

    def _on_resize_change(self, val=None):
        if "커스텀" in self._resize_var.get():
            self._custom_size_frame.grid()
        else:
            self._custom_size_frame.grid_remove()
        self._update_size_estimate()

    def _on_settings_change(self, val=None):
        self._quality_label.configure(text=f"{self._quality_var.get()}%")
        self._update_size_estimate()

    def _on_optimize_toggle(self):
        if self._optimize_var.get():
            self._target_size_frame.grid()
        else:
            self._target_size_frame.grid_remove()

    def _browse_output(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(initialdir=self._output_dir.get())
        if d:
            self._output_dir.set(d)
            settings.set("output_dir", d)
            settings.save()

    def _check_large_images(self):
        """큰 이미지 감지 → 상태 표시줄에 경고"""
        if not self._image_paths:
            return
        max_w = 0
        for path in self._image_paths:
            info = self._get_info(path)
            if info and info[0] > max_w:
                max_w = info[0]

        if max_w >= 2000:
            current_mode = self._resize_var.get()
            if "원본" in current_mode or "큰" in current_mode:
                self._status_label.configure(
                    text=f"⚠ 사진이 {max_w}px로 매우 큽니다! 크기 조절을 'SNS 최적 (640px)'로 변경 권장",
                    text_color="#f59e0b",
                )

    def _update_size_estimate(self):
        if not self._image_paths:
            self._size_est_label.configure(text="예상 용량: -")
            return
        # 대략적 추정
        info = get_image_info(self._image_paths[0])
        if info:
            w, h = info[0], info[1]
        else:
            w, h = 800, 600
        est = estimate_output_size(
            len(self._image_paths), w, h,
            self._format_var.get(),
            self._quality_var.get(),
        )
        self._size_est_label.configure(text=f"예상 용량: ~{format_filesize(est)}")

    # ════════════════════════════════════════
    # 변환 실행
    # ════════════════════════════════════════
    def _get_loop_count(self) -> int:
        val = self._loop_var.get()
        if "무한" in val:
            return 0
        try:
            return int(val.replace("회", ""))
        except Exception:
            return 0

    def _get_resize_mode(self) -> str:
        val = self._resize_var.get()
        if "640" in val:
            return "fixed_width"
        elif "1080" in val:
            return "fixed_width"
        elif "큰" in val:
            return "largest"
        elif "작은" in val:
            return "smallest"
        elif "커스텀" in val:
            return "custom"
        return "none"

    def _get_fixed_width(self) -> int:
        """SNS/고화질 프리셋의 고정 너비 반환"""
        val = self._resize_var.get()
        if "640" in val:
            return 640
        elif "1080" in val:
            return 1080
        return 800

    def _get_bg_color(self) -> str:
        val = self._bg_var.get()
        if "FFFFFF" in val:
            return "#FFFFFF"
        elif "투명" in val:
            return "transparent"
        return "#000000"

    def _build_job(self) -> MergeJob:
        job = MergeJob()
        job.image_paths = list(self._image_paths)
        job.output_format = self._format_var.get()
        job.default_delay = self._delay_var.get()
        job.loop = self._get_loop_count()
        job.resize_mode = self._get_resize_mode()
        job.bg_color = self._get_bg_color()
        job.quality = self._quality_var.get()

        # 개별 프레임 딜레이 반영
        job.frame_delays = [
            self._frame_delays_map.get(i, 0)
            for i in range(len(self._image_paths))
        ]

        # 💬 자막 오버레이 반영 (복사본 전달 - 변환 중 수정되어도 안전)
        job.text_overlays = list(self._subtitles_data)

        if job.resize_mode == "custom":
            try:
                job.custom_width = int(self._cw_entry.get())
                job.custom_height = int(self._ch_entry.get())
            except ValueError:
                job.custom_width = 800
                job.custom_height = 600
        elif job.resize_mode == "fixed_width":
            job.custom_width = self._get_fixed_width()

        ext = "apng" if job.output_format == "apng" else job.output_format
        job.output_path = generate_output_name("animation", ext, self._output_dir.get())
        return job

    def _start_convert(self):
        if self._working:
            return
        if not self._image_paths:
            self._status_label.configure(text="⚠ 이미지를 먼저 추가하세요", text_color="#f59e0b")
            return
        if len(self._image_paths) < 2:
            self._status_label.configure(text="⚠ 2장 이상 필요합니다", text_color="#f59e0b")
            return

        self._working = True
        self._job = self._build_job()
        self._convert_btn.grid_remove()
        self._cancel_btn.grid()
        self._progress.set(0)
        self._status_label.configure(text="변환 시작...", text_color="white")

        # 이전 폴더 열기 버튼 제거
        if hasattr(self, '_open_folder_btn') and self._open_folder_btn:
            try:
                self._open_folder_btn.destroy()
            except Exception:
                pass
            self._open_folder_btn = None

        # 설정 저장
        settings.set("merge_output_format", self._format_var.get())
        settings.set("merge_delay_ms", self._delay_var.get())
        settings.set("merge_quality", self._quality_var.get())
        settings.save()

        # 별도 스레드에서 실행
        t = threading.Thread(target=self._run_convert, daemon=True)
        t.start()

    def _run_convert(self):
        """워커 스레드: 변환 → 최적화(옵션)"""
        def on_progress(pct, msg):
            self.after(0, lambda p=pct, m=msg: self._update_progress(p, m))

        result = merge_images(self._job, on_progress=on_progress)

        # 최적화 옵션이 켜져 있으면 변환 후 자동 최적화
        if result and self._optimize_var.get():
            try:
                target_kb = int(self._target_kb_entry.get())
            except ValueError:
                target_kb = 5000

            on_progress(90, f"🎯 목표 {target_kb}KB 최적화 중...")

            def opt_progress(msg):
                self.after(0, lambda m=msg: self._status_label.configure(text=f"🎯 {m}"))

            optimized = auto_optimize(result, target_kb, on_progress=opt_progress)
            if optimized and optimized != result:
                # 최적화 결과를 원본 위치로 교체 (Windows 파일 잠금 대응)
                import shutil
                try:
                    shutil.copy2(optimized, result)
                    Path(optimized).unlink(missing_ok=True)
                except PermissionError:
                    result = optimized  # 잠금 시 최적화 파일을 그대로 사용
                except Exception:
                    result = optimized

        self.after(0, lambda: self._on_convert_done(result))

    def _update_progress(self, pct: int, msg: str):
        self._progress.set(pct / 100)
        self._status_label.configure(text=msg)

    def _on_convert_done(self, result: Optional[str]):
        self._working = False
        self._cancel_btn.grid_remove()
        self._convert_btn.grid()

        if result and Path(result).exists():
            size = format_filesize(Path(result).stat().st_size)
            self._status_label.configure(
                text=f"✅ 완료! {Path(result).name} ({size})",
                text_color="#22c55e",
            )
            self._progress.set(1.0)
            self._show_open_folder_btn(str(Path(result).parent))
        else:
            # ── 실패/취소 시 progress 리셋 ──
            self._progress.set(0)
            if self._job and self._job.cancelled:
                self._status_label.configure(text="⏹ 취소됨", text_color="#f59e0b")
            else:
                self._status_label.configure(text="❌ 변환 실패", text_color="#ef4444")

    def _cancel_convert(self):
        if self._job:
            self._job.cancelled = True
        self._status_label.configure(text="취소 중...", text_color="#f59e0b")

    def _show_open_folder_btn(self, folder: str):
        """변환 완료 후 폴더 열기 버튼"""
        import subprocess as _sp
        import sys as _sys

        # 이전 버튼 제거
        if hasattr(self, '_open_folder_btn') and self._open_folder_btn:
            self._open_folder_btn.destroy()

        def open_folder():
            try:
                if _sys.platform == "win32":
                    os.startfile(folder)
                elif _sys.platform == "darwin":
                    _sp.Popen(["open", folder])
                else:
                    _sp.Popen(["xdg-open", folder])
            except Exception:
                pass

        # 우측 패널 하단에 버튼 추가 (status_label 아래)
        self._open_folder_btn = ctk.CTkButton(
            self._status_label.master,
            text="📂 출력 폴더 열기",
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#16a34a", hover_color="#15803d",
            command=open_folder,
        )
        self._open_folder_btn.grid(row=24, column=0, padx=12, pady=(4, 8), sticky="ew")

    # ════════════════════════════════════════
    # 💬 자막 관리 (영상 탭과 동일 규칙)
    # ════════════════════════════════════════

    _SUB_COLOR_MAP = {
        "⬜ 흰색": "#FFFFFF",
        "🟨 노랑": "#FFFF00",
        "🟥 빨강": "#FF0000",
        "🟩 초록": "#00FF00",
        "🟦 파랑": "#00BFFF",
        "⬛ 검정": "#000000",
    }

    def _get_sub_color(self) -> str:
        """선택된 자막 색상을 hex로 변환"""
        return self._SUB_COLOR_MAP.get(self._sub_color_var.get(), "#FFFFFF")

    def _update_sub_color_preview(self):
        """색상 미리보기 라벨 업데이트"""
        self._sub_color_preview.configure(text_color=self._get_sub_color())

    def _add_subtitle(self):
        """자막 입력값을 목록에 추가"""
        text = self._sub_entry.get("1.0", "end-1c").strip()
        if not text:
            return

        pos_map = {"하단": "bottom", "중앙": "middle", "상단": "top"}
        position = pos_map.get(self._sub_pos_var.get(), "bottom")

        self._subtitles_data.append({
            "text": text,
            "position": position,
            "size": self._sub_size_var.get(),
            "color": self._get_sub_color(),
            "bold": self._sub_bold_var.get(),
        })
        self._refresh_subtitle_list()
        self._refresh_preview_with_subtitles()  # 미리보기 즉시 갱신

        # 입력 필드 초기화
        self._sub_entry.delete("1.0", "end")

    def _clear_subtitles(self):
        """자막 전체 삭제"""
        self._subtitles_data.clear()
        self._refresh_subtitle_list()
        self._refresh_preview_with_subtitles()  # 미리보기 즉시 갱신

    def _delete_subtitle(self, index: int):
        """자막 개별 삭제"""
        if 0 <= index < len(self._subtitles_data):
            self._subtitles_data.pop(index)
            self._refresh_subtitle_list()
            self._refresh_preview_with_subtitles()  # 미리보기 즉시 갱신

    def _refresh_subtitle_list(self):
        """자막 목록 UI 갱신 (개별 삭제 버튼 포함)"""
        for widget in self._sub_list_frame.winfo_children():
            widget.destroy()

        if not self._subtitles_data:
            ctk.CTkLabel(
                self._sub_list_frame, text="(자막 없음)",
                font=ctk.CTkFont(size=11), text_color="gray50",
                anchor="w",
            ).pack(fill="x")
            return

        pos_kr = {"bottom": "하단", "middle": "중앙", "top": "상단"}
        for i, ov in enumerate(self._subtitles_data):
            row = ctk.CTkFrame(self._sub_list_frame, fg_color="gray25", corner_radius=4, height=26)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            first_line = ov["text"].split("\n")[0]
            txt_short = first_line[:18] + "…" if len(first_line) > 18 else first_line
            pos = pos_kr.get(ov["position"], ov["position"])
            info = f"{i+1}. {pos} {ov['size']}px {txt_short}"

            ctk.CTkLabel(
                row, text=info,
                font=ctk.CTkFont(size=10),
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=4)

            ctk.CTkButton(
                row, text="✕", width=22, height=20,
                font=ctk.CTkFont(size=10),
                fg_color="#dc2626", hover_color="#b91c1c",
                command=lambda idx=i: self._delete_subtitle(idx),
            ).pack(side="right", padx=2)

    # ════════════════════════════════════════
    # 자막 미리보기 렌더링 (영상 탭의 _draw_subtitles_on_frame 이식)
    # ════════════════════════════════════════

    def _refresh_preview_with_subtitles(self):
        """자막 변경 시 현재 미리보기 프레임 다시 그리기"""
        if self._image_paths:
            # 현재 표시 중이던 프레임 재렌더링
            idx = self._preview_current_index
            if idx >= len(self._image_paths):
                idx = 0
            self._show_preview_frame(idx)

    def _draw_subtitles_on_preview(self, img):
        """
        미리보기 이미지에 자막을 합성해서 반환.
        실제 변환 결과와 동일한 스타일로 그림 (480p 기준 정규화).
        """
        if not self._subtitles_data:
            return img

        try:
            from PIL import ImageDraw, ImageFont, Image as _PImg

            # RGB → RGBA 변환
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            overlay = _PImg.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            for sub in self._subtitles_data:
                text = sub.get("text", "")
                if not text.strip():
                    continue

                # 480p 기준 정규화 (실제 변환과 동일 공식)
                preview_size = max(14, int(sub.get("size", 28) * img.height / 480))

                # 폰트 로드 (여러 경로 시도)
                font = None
                bold = sub.get("bold", True)
                if bold:
                    font_paths = [
                        "C:/Windows/Fonts/malgunbd.ttf",
                        "malgunbd.ttf", "arialbd.ttf",
                        "C:/Windows/Fonts/malgun.ttf",
                        "malgun.ttf", "arial.ttf",
                    ]
                else:
                    font_paths = [
                        "C:/Windows/Fonts/malgun.ttf",
                        "malgun.ttf", "gulim.ttc", "arial.ttf",
                    ]

                for fp in font_paths:
                    try:
                        font = ImageFont.truetype(fp, preview_size)
                        break
                    except (OSError, IOError):
                        continue

                if font is None:
                    try:
                        font = ImageFont.load_default(size=preview_size)
                    except TypeError:
                        font = ImageFont.load_default()

                # 텍스트 크기 측정 (멀티라인)
                bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=4)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                padding = max(6, int(preview_size * 0.3))

                # 위치 계산
                position = sub.get("position", "bottom")
                x = (img.width - tw) // 2
                if position == "top":
                    y = int(img.height * 0.05)
                elif position == "middle":
                    y = (img.height - th) // 2
                else:  # bottom
                    y = img.height - th - int(img.height * 0.05)

                # y 보정 (bbox[1]이 0이 아닐 수 있음)
                text_y = y - bbox[1]

                # 반투명 검정 배경 박스
                box_x0 = max(0, x - padding)
                box_y0 = max(0, y - padding // 2)
                box_x1 = min(img.width, x + tw + padding)
                box_y1 = min(img.height, y + th + padding // 2)
                draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=(0, 0, 0, 140))

                # 테두리 (검정 외곽선)
                color = sub.get("color", "#FFFFFF")
                outline_width = max(1, preview_size // 16)
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw.multiline_text(
                                (x + dx, text_y + dy), text,
                                font=font, fill=(0, 0, 0, 255),
                                align="center", spacing=4,
                            )

                # 본문 텍스트
                draw.multiline_text(
                    (x, text_y), text,
                    font=font, fill=color,
                    align="center", spacing=4,
                )

            # 원본 이미지 위에 overlay 합성
            result = _PImg.alpha_composite(img, overlay)
            overlay.close()
            return result

        except Exception:
            return img  # 실패해도 원본 반환 (안전)
