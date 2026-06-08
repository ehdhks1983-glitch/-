"""
ui_video_tab.py - 영상 → GIF/WebP/APNG 변환 탭 UI
파일 선택, 구간 편집, 설정, 미리보기
"""

import os
import sys
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from config import settings
from utils import (
    is_video_file, format_filesize, generate_output_name,
    ffmpeg_available, find_ffmpeg, VIDEO_EXTS,
)
from video_converter import (
    VideoInfo, ConvertJob, Subtitle, probe_video, convert_video,
    estimate_video_output_size,
)
from optimizer import auto_optimize


# ════════════════════════════════════════
# 자막 미리보기 헬퍼
# ════════════════════════════════════════

def _PImg_new_rgba(size):
    """투명 RGBA 이미지 생성"""
    from PIL import Image
    return Image.new('RGBA', size, (0, 0, 0, 0))


def _PImg_alpha_composite(base, overlay):
    """두 RGBA 이미지 합성"""
    from PIL import Image
    return Image.alpha_composite(base, overlay)


def _hex_to_rgba(hex_color: str, alpha: int = 255):
    """#RRGGBB or #RRGGBBAA → (R, G, B, A)"""
    s = hex_color.lstrip('#')
    if len(s) == 6:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b, alpha)
    elif len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    return (255, 255, 255, alpha)



class VideoTab(ctk.CTkFrame):
    """영상 변환 탭"""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._video_path: Optional[str] = None
        self._video_info: Optional[VideoInfo] = None
        self._job: Optional[ConvertJob] = None
        self._working: bool = False

        # 미리보기 상태
        self._preview_current_time: float = 0.0
        self._preview_playing: bool = False
        self._preview_after_id = None
        self._preview_photo = None  # CTkImage 참조 유지 (GC 방지)
        self._preview_scrub_after_id = None  # 스크러빙 디바운스
        self._preview_width_px: int = 640  # 미리보기 렌더 크기

        # 프레임 캐시 (영상 로드 시 일괄 추출)
        self._cached_frames = []   # [(time_sec, PIL.Image), ...]
        self._cache_fps: float = 2.0  # 캐시 추출 FPS
        self._cache_temp_dir = None

        self._build_ui()

    def _build_ui(self):
        # 2-Column: 좌(영상 정보 + 미리보기) / 우(설정)
        self.grid_columnconfigure(0, weight=2, minsize=450)
        self.grid_columnconfigure(1, weight=1, minsize=280)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # ════════════════════════════════════════
    # 좌측: 영상 선택 + 정보 + 구간
    # ════════════════════════════════════════
    def _build_left_panel(self):
        left = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        left.grid_columnconfigure(0, weight=1)

        # ── 파일 선택 ──
        file_frame = ctk.CTkFrame(left, fg_color="transparent")
        file_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        self._open_btn = ctk.CTkButton(
            file_frame, text="📂 영상 파일 열기", height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_video,
        )
        self._open_btn.pack(side="left", padx=(0, 8))

        self._file_label = ctk.CTkLabel(
            file_frame, text="파일을 선택하세요",
            font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._file_label.pack(side="left", fill="x", expand=True)

        # ── 영상 정보 ──
        self._info_frame = ctk.CTkFrame(left, fg_color="gray20", corner_radius=8)
        self._info_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=8)

        self._info_label = ctk.CTkLabel(
            self._info_frame,
            text="영상 정보가 여기에 표시됩니다",
            font=ctk.CTkFont(size=12),
            text_color="gray50",
        )
        self._info_label.pack(padx=12, pady=10)

        # ── 🎬 영상 미리보기 영역 ──
        preview_wrapper = ctk.CTkFrame(left, fg_color="black", corner_radius=8, height=280)
        preview_wrapper.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 4))
        preview_wrapper.grid_propagate(False)
        preview_wrapper.grid_columnconfigure(0, weight=1)
        preview_wrapper.grid_rowconfigure(0, weight=1)

        self._preview_label = ctk.CTkLabel(
            preview_wrapper, text="📺 영상을 열면 미리보기가 표시됩니다",
            font=ctk.CTkFont(size=13), text_color="gray50",
        )
        self._preview_label.grid(row=0, column=0, sticky="nsew")

        # ── 재생 컨트롤 ──
        play_ctrl = ctk.CTkFrame(left, fg_color="transparent")
        play_ctrl.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 4))

        self._play_btn = ctk.CTkButton(
            play_ctrl, text="▶ 재생", width=70, height=28,
            font=ctk.CTkFont(size=12),
            command=self._toggle_play,
        )
        self._play_btn.pack(side="left", padx=(0, 4))

        # 프리뷰 시간 슬라이더
        self._preview_slider = ctk.CTkSlider(
            play_ctrl, from_=0, to=100, number_of_steps=1000,
            command=self._on_preview_slider,
        )
        self._preview_slider.pack(side="left", fill="x", expand=True, padx=4)
        self._preview_slider.set(0)

        self._preview_time_label = ctk.CTkLabel(
            play_ctrl, text="0.0 / 0.0s",
            font=ctk.CTkFont(size=11), text_color="gray60", width=70,
        )
        self._preview_time_label.pack(side="left", padx=(4, 0))

        # 구간 지정 버튼
        mark_frame = ctk.CTkFrame(left, fg_color="transparent")
        mark_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))

        ctk.CTkButton(
            mark_frame, text="⏮ 여기부터 시작", height=28,
            font=ctk.CTkFont(size=12),
            fg_color="#16a34a", hover_color="#15803d",
            command=self._mark_start,
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        ctk.CTkButton(
            mark_frame, text="여기까지 끝 ⏭", height=28,
            font=ctk.CTkFont(size=12),
            fg_color="#dc2626", hover_color="#b91c1c",
            command=self._mark_end,
        ).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # ── 구간 선택 ──
        ctk.CTkLabel(left, text="✂️ 구간 선택",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=5, column=0, sticky="w", padx=12, pady=(8, 2))

        range_frame = ctk.CTkFrame(left, fg_color="transparent")
        range_frame.grid(row=6, column=0, sticky="ew", padx=12, pady=4)

        # 시작 시간
        ctk.CTkLabel(range_frame, text="시작:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=(0, 4))
        self._start_entry = ctk.CTkEntry(range_frame, width=80, height=28,
                                          font=ctk.CTkFont(size=12), placeholder_text="0.0")
        self._start_entry.grid(row=0, column=1, padx=4)
        ctk.CTkLabel(range_frame, text="초", font=ctk.CTkFont(size=11),
                     text_color="gray50").grid(row=0, column=2, padx=(0, 16))

        # 끝 시간
        ctk.CTkLabel(range_frame, text="끝:", font=ctk.CTkFont(size=12)).grid(row=0, column=3, padx=(0, 4))
        self._end_entry = ctk.CTkEntry(range_frame, width=80, height=28,
                                        font=ctk.CTkFont(size=12), placeholder_text="끝까지")
        self._end_entry.grid(row=0, column=4, padx=4)
        ctk.CTkLabel(range_frame, text="초", font=ctk.CTkFont(size=11),
                     text_color="gray50").grid(row=0, column=5)

        # 시작 시간 슬라이더
        start_sl_frame = ctk.CTkFrame(left, fg_color="transparent")
        start_sl_frame.grid(row=7, column=0, sticky="ew", padx=12, pady=(4, 0))
        ctk.CTkLabel(start_sl_frame, text="시작",
                     font=ctk.CTkFont(size=11), text_color="gray50", width=30).pack(side="left")
        self._start_slider = ctk.CTkSlider(
            start_sl_frame, from_=0, to=100, number_of_steps=100,
            command=self._on_start_slider,
        )
        self._start_slider.pack(side="left", fill="x", expand=True, padx=4)
        self._start_slider.set(0)

        # 끝 시간 슬라이더
        end_sl_frame = ctk.CTkFrame(left, fg_color="transparent")
        end_sl_frame.grid(row=8, column=0, sticky="ew", padx=12, pady=(2, 4))
        ctk.CTkLabel(end_sl_frame, text="끝",
                     font=ctk.CTkFont(size=11), text_color="gray50", width=30).pack(side="left")
        self._end_slider = ctk.CTkSlider(
            end_sl_frame, from_=0, to=100, number_of_steps=100,
            command=self._on_end_slider,
        )
        self._end_slider.pack(side="left", fill="x", expand=True, padx=4)
        self._end_slider.set(100)

        self._duration_label = ctk.CTkLabel(
            left, text="구간: 0.0초 ~ 끝",
            font=ctk.CTkFont(size=11), text_color="gray50",
        )
        self._duration_label.grid(row=9, column=0, sticky="w", padx=12, pady=(0, 4))

        # ── 용량 경고 ──
        self._warn_label = ctk.CTkLabel(
            left, text="",
            font=ctk.CTkFont(size=11), text_color="#f59e0b",
        )
        self._warn_label.grid(row=10, column=0, sticky="w", padx=12, pady=(0, 4))

        # ── 진행률 ──
        self._progress = ctk.CTkProgressBar(left, height=14)
        self._progress.grid(row=11, column=0, sticky="ew", padx=12, pady=8)
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(
            left, text="",
            font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._status_label.grid(row=12, column=0, sticky="w", padx=12, pady=(0, 12))

    # ════════════════════════════════════════
    # 우측: 설정 패널
    # ════════════════════════════════════════
    def _build_right_panel(self):
        right = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        pad = {"padx": 12, "pady": (4, 2), "sticky": "ew"}

        # ── 🛡️ 안전 모드 (최상단) ──
        safe_frame = ctk.CTkFrame(right, fg_color="#1e3a5f", corner_radius=8)
        safe_frame.grid(row=0, column=0, padx=12, pady=(8, 12), sticky="ew")

        self._safe_mode_var = ctk.BooleanVar(value=True)
        safe_check = ctk.CTkCheckBox(
            safe_frame, text="🛡️ 안전 모드 (권장)",
            variable=self._safe_mode_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_safe_mode_toggle,
        )
        safe_check.pack(anchor="w", padx=10, pady=(8, 2))

        ctk.CTkLabel(
            safe_frame,
            text="영상 크기·길이·PC 메모리에 맞춰\n자동으로 최적 설정 적용",
            font=ctk.CTkFont(size=10),
            text_color="#93c5fd",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # ── 출력 포맷 ──
        ctk.CTkLabel(right, text="📦 출력 포맷",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=1, column=0, **pad)

        _fmt = settings.get("video_output_format")
        self._format_var = ctk.StringVar(value=_fmt if _fmt in ("gif", "webp", "apng") else "gif")
        fmt_frame = ctk.CTkFrame(right, fg_color="transparent")
        fmt_frame.grid(row=2, column=0, **pad)
        for i, (text, val) in enumerate([("GIF", "gif"), ("WebP", "webp"), ("APNG", "apng")]):
            ctk.CTkRadioButton(
                fmt_frame, text=text, variable=self._format_var, value=val,
                font=ctk.CTkFont(size=12),
                command=self._on_settings_change,
            ).grid(row=0, column=i, padx=8)

        # 🎚️ 화질 프리셋 — 품질·용량을 한 번에 (GIF에 적용)
        self._qmode_var = ctk.StringVar(value=settings.get("video_quality_mode") or "🔵 균형")
        ctk.CTkSegmentedButton(
            fmt_frame,
            values=["🟢 최고화질", "🔵 균형", "🟡 빠른로딩"],
            variable=self._qmode_var,
            font=ctk.CTkFont(size=11),
            command=self._on_settings_change,
        ).grid(row=1, column=0, columnspan=3, padx=4, pady=(8, 2), sticky="ew")
        ctk.CTkLabel(
            fmt_frame,
            text="💡 블로그·웹은 WebP 추천 — 같은 화질에 용량 30~50%↓ (로딩 빠름)",
            font=ctk.CTkFont(size=10), text_color="gray55",
        ).grid(row=2, column=0, columnspan=3, padx=4, sticky="w")

        # ── FPS ──
        ctk.CTkLabel(right, text="🎞️ FPS",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=3, column=0, **pad)

        self._fps_var = ctk.StringVar(value="15")
        self._fps_menu = ctk.CTkOptionMenu(
            right, values=["원본", "10", "12", "15", "20", "24"],
            variable=self._fps_var,
            font=ctk.CTkFont(size=12),
            command=self._on_settings_change,
        )
        self._fps_menu.grid(row=4, column=0, **pad)

        # ── 해상도 ──
        ctk.CTkLabel(right, text="📐 해상도",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=5, column=0, **pad)

        self._res_var = ctk.StringVar(value="480p")
        self._res_menu = ctk.CTkOptionMenu(
            right, values=["원본", "720p", "480p", "360p", "240p", "커스텀"],
            variable=self._res_var,
            font=ctk.CTkFont(size=12),
            command=self._on_res_change,
        )
        self._res_menu.grid(row=6, column=0, **pad)

        # 커스텀 너비 (기본 숨김)
        self._custom_w_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._custom_w_frame.grid(row=7, column=0, **pad)
        self._custom_w_frame.grid_remove()

        ctk.CTkLabel(self._custom_w_frame, text="너비:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._custom_w_entry = ctk.CTkEntry(self._custom_w_frame, width=70, height=28,
                                             font=ctk.CTkFont(size=12))
        self._custom_w_entry.insert(0, "480")
        self._custom_w_entry.pack(side="left", padx=4)
        ctk.CTkLabel(self._custom_w_frame, text="px (높이 자동)",
                     font=ctk.CTkFont(size=11), text_color="gray50").pack(side="left")

        # ── 속도 ──
        ctk.CTkLabel(right, text="⏩ 속도",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=8, column=0, **pad)

        self._speed_var = ctk.StringVar(value="1.0x")
        self._speed_menu = ctk.CTkOptionMenu(
            right, values=["0.5x", "0.75x", "1.0x", "1.5x", "2.0x"],
            variable=self._speed_var,
            font=ctk.CTkFont(size=12),
            command=self._on_settings_change,
        )
        self._speed_menu.grid(row=9, column=0, **pad)

        # ── 품질 ──
        ctk.CTkLabel(right, text="💎 품질",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=10, column=0, **pad)

        self._quality_var = ctk.IntVar(value=settings.get("video_quality"))
        q_frame = ctk.CTkFrame(right, fg_color="transparent")
        q_frame.grid(row=11, column=0, **pad)

        self._quality_slider = ctk.CTkSlider(
            q_frame, from_=10, to=100,
            variable=self._quality_var,
            command=self._on_settings_change,
            width=160,
        )
        self._quality_slider.pack(side="left", padx=(0, 8))
        self._quality_label = ctk.CTkLabel(
            q_frame, text=f"{self._quality_var.get()}%",
            font=ctk.CTkFont(size=12),
        )
        self._quality_label.pack(side="left")

        # ── 반복 ──
        ctk.CTkLabel(right, text="🔁 반복",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=12, column=0, **pad)

        self._loop_var = ctk.StringVar(value="무한 반복")
        self._loop_menu = ctk.CTkOptionMenu(
            right, values=["무한 반복", "1회", "2회", "3회", "5회"],
            variable=self._loop_var,
            font=ctk.CTkFont(size=12),
        )
        self._loop_menu.grid(row=13, column=0, **pad)

        # ── 목표 용량 ──
        ctk.CTkLabel(right, text="🎯 목표 용량",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=14, column=0, **pad)

        opt_frame = ctk.CTkFrame(right, fg_color="transparent")
        opt_frame.grid(row=15, column=0, **pad)

        self._optimize_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opt_frame, text="자동 최적화",
            variable=self._optimize_var,
            font=ctk.CTkFont(size=12),
            command=self._on_optimize_toggle,
        ).pack(side="left")

        self._target_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._target_frame.grid(row=16, column=0, **pad)
        self._target_frame.grid_remove()

        ctk.CTkLabel(self._target_frame, text="목표:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._target_kb_entry = ctk.CTkEntry(self._target_frame, width=70, height=28,
                                              font=ctk.CTkFont(size=12))
        self._target_kb_entry.insert(0, "5000")
        self._target_kb_entry.pack(side="left", padx=4)
        ctk.CTkLabel(self._target_frame, text="KB",
                     font=ctk.CTkFont(size=11), text_color="gray50").pack(side="left")

        # ── 💬 자막 섹션 ──
        ctk.CTkLabel(right, text="💬 자막 (선택)",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=17, column=0, **pad)

        sub_container = ctk.CTkFrame(right, fg_color="gray20", corner_radius=8)
        sub_container.grid(row=18, column=0, padx=12, pady=(2, 4), sticky="ew")

        # 자막 입력
        sub_text_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_text_frame.pack(fill="x", padx=8, pady=(8, 4))

        self._sub_text_entry = ctk.CTkTextbox(
            sub_text_frame, font=ctk.CTkFont(size=12), height=50,
            wrap="word",
        )
        self._sub_text_entry.pack(fill="x")

        ctk.CTkLabel(
            sub_text_frame, text="💡 Enter로 줄바꿈 가능",
            font=ctk.CTkFont(size=9), text_color="gray50", anchor="w",
        ).pack(anchor="w")

        # 시간 + 위치
        sub_time_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_time_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkLabel(sub_time_frame, text="시작",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self._sub_start_entry = ctk.CTkEntry(sub_time_frame, width=45, height=24,
                                              font=ctk.CTkFont(size=11))
        self._sub_start_entry.pack(side="left", padx=2)
        ctk.CTkLabel(sub_time_frame, text="~끝",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        self._sub_end_entry = ctk.CTkEntry(sub_time_frame, width=45, height=24,
                                            font=ctk.CTkFont(size=11))
        self._sub_end_entry.pack(side="left", padx=2)

        self._sub_pos_var = ctk.StringVar(value="하단")
        ctk.CTkOptionMenu(
            sub_time_frame, values=["하단", "중앙", "상단"],
            variable=self._sub_pos_var, width=80, height=24,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(4, 0))

        # 크기 + 굵기
        sub_style_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_style_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkLabel(sub_style_frame, text="크기",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self._sub_size_var = ctk.IntVar(value=32)
        self._sub_size_slider = ctk.CTkSlider(
            sub_style_frame, from_=16, to=72,
            variable=self._sub_size_var, width=100, height=16,
        )
        self._sub_size_slider.pack(side="left", padx=2)
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

        # 색상 선택
        sub_color_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        sub_color_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkLabel(sub_color_frame, text="색상",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        self._sub_color_var = ctk.StringVar(value="⬜ 흰색")
        self._sub_color_menu = ctk.CTkOptionMenu(
            sub_color_frame,
            values=["⬜ 흰색", "🟨 노랑", "🟥 빨강", "🟩 초록", "🟦 파랑", "⬛ 검정"],
            variable=self._sub_color_var,
            width=110, height=24,
            font=ctk.CTkFont(size=11),
        )
        self._sub_color_menu.pack(side="left", padx=2)

        # 색상 미리보기 (실시간)
        self._sub_color_preview = ctk.CTkLabel(
            sub_color_frame, text="  Aa  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="gray30", corner_radius=4,
            width=40, height=22,
        )
        self._sub_color_preview.pack(side="left", padx=4)
        self._sub_color_var.trace_add("write", lambda *_: self._update_color_preview())

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

        # 자막 목록 (개별 삭제 가능)
        self._sub_list_frame = ctk.CTkFrame(sub_container, fg_color="transparent")
        self._sub_list_frame.pack(fill="x", padx=8, pady=(0, 4))

        self._sub_empty_label = ctk.CTkLabel(
            self._sub_list_frame, text="(자막 없음)",
            font=ctk.CTkFont(size=11), text_color="gray50",
            anchor="w",
        )
        self._sub_empty_label.pack(fill="x")

        # 미리보기 힌트
        ctk.CTkLabel(
            sub_container,
            text="💡 자막 추가 시 왼쪽 미리보기에서 즉시 확인 가능",
            font=ctk.CTkFont(size=10), text_color="#3b82f6",
            anchor="w", justify="left",
        ).pack(fill="x", padx=8, pady=(0, 8))

        self._subtitles_data = []  # List[Subtitle]

        # ── ✂️ 자동 분할 (멀티 GIF) ──
        ctk.CTkLabel(right, text="✂️ 자동 분할",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=19, column=0, **pad)

        split_container = ctk.CTkFrame(right, fg_color="gray20", corner_radius=8)
        split_container.grid(row=20, column=0, padx=12, pady=(2, 4), sticky="ew")

        # 체크박스
        self._split_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            split_container, text="영상을 여러 개로 나누기",
            variable=self._split_var,
            font=ctk.CTkFont(size=12),
            command=self._on_split_toggle,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        # 분할 설정 영역 (체크 시 표시)
        self._split_settings = ctk.CTkFrame(split_container, fg_color="transparent")
        self._split_settings.pack(fill="x", padx=8, pady=(0, 8))
        self._split_settings.pack_forget()  # 기본 숨김

        # 분할 방식 선택
        mode_frame = ctk.CTkFrame(self._split_settings, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(4, 2))

        self._split_mode_var = ctk.StringVar(value="count")
        ctk.CTkRadioButton(
            mode_frame, text="개수로 나누기", value="count",
            variable=self._split_mode_var,
            font=ctk.CTkFont(size=11),
            command=self._on_split_mode_change,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(
            mode_frame, text="초 단위로 나누기", value="duration",
            variable=self._split_mode_var,
            font=ctk.CTkFont(size=11),
            command=self._on_split_mode_change,
        ).pack(side="left")

        # 빠른 선택 버튼
        self._split_quick_frame = ctk.CTkFrame(self._split_settings, fg_color="transparent")
        self._split_quick_frame.pack(fill="x", pady=2)

        for n in [3, 5, 10]:
            ctk.CTkButton(
                self._split_quick_frame, text=f"{n}개",
                width=50, height=24,
                font=ctk.CTkFont(size=11),
                fg_color="gray30", hover_color="gray40",
                command=lambda v=n: self._set_split_count(v),
            ).pack(side="left", padx=2)

        ctk.CTkLabel(self._split_quick_frame, text="직접:",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        self._split_count_entry = ctk.CTkEntry(
            self._split_quick_frame, width=40, height=24,
            font=ctk.CTkFont(size=11),
        )
        self._split_count_entry.insert(0, "5")
        self._split_count_entry.pack(side="left", padx=2)
        self._split_count_entry.bind("<KeyRelease>", lambda e: self._update_split_preview())

        # 초 단위 입력 (숨겨둠)
        self._split_dur_frame = ctk.CTkFrame(self._split_settings, fg_color="transparent")

        ctk.CTkLabel(self._split_dur_frame, text="구간당:",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self._split_dur_entry = ctk.CTkEntry(
            self._split_dur_frame, width=50, height=24,
            font=ctk.CTkFont(size=11),
        )
        self._split_dur_entry.insert(0, "10")
        self._split_dur_entry.pack(side="left", padx=2)
        ctk.CTkLabel(self._split_dur_frame, text="초씩",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._split_dur_entry.bind("<KeyRelease>", lambda e: self._update_split_preview())

        # 겹치기
        overlap_frame = ctk.CTkFrame(self._split_settings, fg_color="transparent")
        overlap_frame.pack(fill="x", pady=2)

        ctk.CTkLabel(overlap_frame, text="겹치기:",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self._split_overlap_entry = ctk.CTkEntry(
            overlap_frame, width=40, height=24,
            font=ctk.CTkFont(size=11),
        )
        self._split_overlap_entry.insert(0, "0.5")
        self._split_overlap_entry.pack(side="left", padx=2)
        ctk.CTkLabel(overlap_frame, text="초 (이전 끝과 겹침)",
                     font=ctk.CTkFont(size=10), text_color="gray50").pack(side="left", padx=2)

        # 예상 결과
        self._split_preview_label = ctk.CTkLabel(
            self._split_settings, text="",
            font=ctk.CTkFont(size=11), text_color="#3b82f6",
            anchor="w", justify="left",
        )
        self._split_preview_label.pack(fill="x", pady=(4, 0))

        # 자막 적용 옵션
        self._split_sub_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self._split_settings, text="모든 분할에 자막 적용",
            variable=self._split_sub_var,
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(4, 0))

        # ── 출력 폴더 ──
        ctk.CTkLabel(right, text="📂 출력 폴더",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=21, column=0, **pad)

        out_frame = ctk.CTkFrame(right, fg_color="transparent")
        out_frame.grid(row=22, column=0, **pad)

        self._output_dir = ctk.StringVar(value=settings.get("output_dir"))
        self._out_entry = ctk.CTkEntry(out_frame, textvariable=self._output_dir,
                                        font=ctk.CTkFont(size=11), height=28)
        self._out_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(out_frame, text="📁", width=30, height=28,
                      command=self._browse_output).pack(side="right")

        # ── 변환 버튼 ──
        spacer = ctk.CTkFrame(right, fg_color="transparent", height=12)
        spacer.grid(row=23, column=0)

        self._convert_btn = ctk.CTkButton(
            right, text="🚀 변환 시작", height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._start_convert,
        )
        self._convert_btn.grid(row=24, column=0, padx=12, pady=8, sticky="ew")

        self._cancel_btn = ctk.CTkButton(
            right, text="⏹ 취소", height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#dc2626", hover_color="#b91c1c",
            command=self._cancel_convert,
        )
        self._cancel_btn.grid(row=25, column=0, padx=12, pady=(0, 4), sticky="ew")
        self._cancel_btn.grid_remove()

        # ── 예상 용량 ──
        self._est_label = ctk.CTkLabel(
            right, text="예상 용량: -",
            font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._est_label.grid(row=26, column=0, padx=12, pady=(4, 8), sticky="w")

    # ════════════════════════════════════════
    # 파일 열기 + 정보
    # ════════════════════════════════════════
    def _open_video(self):
        from tkinter import filedialog

        if not ffmpeg_available():
            self._status_label.configure(
                text="⚠ FFmpeg가 설치되어 있지 않습니다. ffmpeg/ 폴더에 넣거나 PATH에 추가하세요.",
                text_color="#ef4444",
            )
            return

        exts = " ".join(f"*{e}" for e in VIDEO_EXTS)
        path = filedialog.askopenfilename(
            title="영상 파일 선택",
            filetypes=[("영상 파일", exts), ("모든 파일", "*.*")],
        )
        if not path:
            return

        self._video_path = path
        self._cleanup_cache()  # 이전 영상 캐시 정리
        name = Path(path).name
        if len(name) > 40:
            name = name[:37] + "..."
        self._file_label.configure(text=name, text_color="white")
        self._status_label.configure(text="영상 분석 중...", text_color="gray50")

        # 별도 스레드에서 probe
        threading.Thread(target=self._probe_video, daemon=True).start()

    def _probe_video(self):
        info = probe_video(self._video_path)
        self.after(0, lambda: self._on_probe_done(info))

    def _on_probe_done(self, info: Optional[VideoInfo]):
        if not info:
            self._info_label.configure(text="❌ 영상 정보를 읽을 수 없습니다", text_color="#ef4444")
            self._video_info = None
            return

        self._video_info = info
        self._info_label.configure(
            text=f"🎬 {info.summary()}\n    코덱: {info.codec}",
            text_color="white",
        )

        # 슬라이더 범위 업데이트
        max_dur = max(1, int(info.duration))
        self._start_slider.configure(to=max_dur)
        self._start_slider.set(0)
        self._end_slider.configure(to=max_dur)
        self._end_slider.set(max_dur)
        self._end_entry.configure(placeholder_text=f"{info.duration:.1f}")
        self._start_entry.delete(0, "end")
        self._end_entry.delete(0, "end")

        # 미리보기 슬라이더 업데이트
        self._preview_slider.configure(to=info.duration, number_of_steps=max(100, int(info.duration * 10)))
        self._preview_slider.set(0)
        self._preview_current_time = 0.0
        self._update_preview_time_label()

        # 첫 프레임 로드 + 전체 프레임 캐시 추출
        self._status_label.configure(text="📺 미리보기 프레임 추출 중...", text_color="#3b82f6")
        threading.Thread(target=self._extract_preview_cache, daemon=True).start()

        # FPS 옵션에 원본 값 반영
        orig_fps = f"원본 ({int(info.fps)})"
        self._fps_menu.configure(values=[orig_fps, "10", "12", "15", "20", "24"])

        # ── 🎯 자동 최적 설정 (안전 모드 켜져 있을 때) ──
        if getattr(self, '_safe_mode_var', None) and self._safe_mode_var.get():
            self._auto_tune_settings(info)
        else:
            self._fps_var.set(orig_fps)

        # 용량 경고
        self._update_warn()
        self._update_estimate()
        self._status_label.configure(text="✅ 영상 로드 완료", text_color="#22c55e")

    # ════════════════════════════════════════
    # 🎬 영상 미리보기 (프레임 캐시 방식)
    # ════════════════════════════════════════
    def _extract_preview_cache(self):
        """영상 로드 시: ① 첫 프레임을 빠르게 표시 → ② 스크럽/재생용 프레임 캐시(상한)"""
        if not self._video_path or not self._video_info:
            return

        try:
            import subprocess as _sp
            import tempfile as _tf
            from PIL import Image as _PImg

            ff = find_ffmpeg()
            if not ff:
                return

            # 이전 캐시 정리 + 임시 폴더
            self._cleanup_cache()
            self._cache_temp_dir = _tf.mkdtemp(prefix="gifmaker_preview_")

            # 미리보기 크기
            src_w = self._video_info.width
            src_h = self._video_info.height
            scale_w = min(640, src_w) if src_w else 640
            scale_h = int(src_h * (scale_w / max(1, src_w))) if src_w else 360
            scale_h = max(2, scale_h - (scale_h % 2))

            # ── ① 첫 프레임 즉시 표시 (입력 앞 -ss = 전체 디코드 없이 빠른 시크 → 4K/대용량도 1~2초) ──
            self._quick_preview_frame(ff, scale_w, scale_h)

            # ── ② 스크럽/재생용 프레임 캐시 (총 프레임 수 상한 → 대용량/긴 영상 보호) ──
            duration = max(0.1, self._video_info.duration)
            cache_fps = 4 if duration <= 10 else 2 if duration <= 60 else 1
            max_frames = 150
            if duration * cache_fps > max_frames:
                cache_fps = max(0.2, max_frames / duration)  # 긴 영상은 더 듬성하게
            self._cache_fps = cache_fps

            output_pattern = os.path.join(self._cache_temp_dir, "f_%05d.jpg")
            cmd = [
                ff, "-y",
                "-i", self._video_path,
                "-vf", f"fps={cache_fps},scale={scale_w}:{scale_h}",
                "-q:v", "5",  # 중간 품질 (빠른 추출)
                output_pattern,
            ]
            kwargs = {"stdout": _sp.PIPE, "stderr": _sp.PIPE, "timeout": 180}
            if sys.platform == "win32":
                si = _sp.STARTUPINFO()
                si.dwFlags |= _sp.STARTF_USESHOWWINDOW
                si.wShowWindow = _sp.SW_HIDE
                kwargs["startupinfo"] = si

            try:
                _sp.run(cmd, **kwargs)
            except Exception:
                pass  # 시간 초과/실패해도 ①의 첫 프레임은 이미 표시됨

            # 추출된 프레임 로드
            frame_files = sorted(Path(self._cache_temp_dir).glob("f_*.jpg"))
            self._cached_frames = []
            for i, fp in enumerate(frame_files):
                time_sec = i / cache_fps
                try:
                    img = _PImg.open(str(fp))
                    img.load()
                    frame_copy = img.copy()
                    img.close()
                    self._cached_frames.append((time_sec, frame_copy))
                except Exception:
                    pass

            total = len(self._cached_frames)
            if total > 0:
                self.after(0, lambda: self._show_cached_frame(self._preview_current_time))
                self.after(0, lambda t=total: self._status_label.configure(
                    text=f"✅ 영상 로드 완료 ({t}프레임 캐시됨)",
                    text_color="#22c55e",
                ))
            else:
                # 캐시는 비어도 첫 프레임은 떠 있음
                self.after(0, lambda: self._status_label.configure(
                    text="✅ 영상 로드 완료", text_color="#22c55e",
                ))

        except Exception:
            self.after(0, lambda: self._status_label.configure(
                text="✅ 영상 로드 완료", text_color="#22c55e",
            ))

    def _quick_preview_frame(self, ff, scale_w, scale_h):
        """첫 프레임 1장만 빠르게 추출해 즉시 표시 (대용량·4K·긴 영상 대응)"""
        try:
            import subprocess as _sp
            from PIL import Image as _PImg

            one = os.path.join(self._cache_temp_dir, "first.jpg")
            seek = "1" if (self._video_info.duration or 0) > 2 else "0"
            cmd = [
                ff, "-y",
                "-ss", seek,           # 입력 앞 시크 = 전체 디코드 없이 즉시
                "-i", self._video_path,
                "-frames:v", "1",
                "-vf", f"scale={scale_w}:{scale_h}",
                "-q:v", "4",
                one,
            ]
            kwargs = {"stdout": _sp.PIPE, "stderr": _sp.PIPE, "timeout": 30}
            if sys.platform == "win32":
                si = _sp.STARTUPINFO()
                si.dwFlags |= _sp.STARTF_USESHOWWINDOW
                si.wShowWindow = _sp.SW_HIDE
                kwargs["startupinfo"] = si

            _sp.run(cmd, **kwargs)
            if os.path.exists(one):
                img = _PImg.open(one)
                img.load()
                fc = img.copy()
                img.close()
                self.after(0, lambda im=fc: self._set_preview_image(im))
                self.after(0, lambda: self._status_label.configure(
                    text="✅ 미리보기 표시 (프레임 캐시 준비 중...)",
                    text_color="#22c55e",
                ))
        except Exception:
            pass

    def _cleanup_cache(self):
        """캐시 프레임 메모리 + 임시 폴더 정리"""
        for _, img in self._cached_frames:
            try:
                img.close()
            except Exception:
                pass
        self._cached_frames = []

        if self._cache_temp_dir and os.path.exists(self._cache_temp_dir):
            try:
                import shutil
                shutil.rmtree(self._cache_temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._cache_temp_dir = None

    def _find_nearest_frame(self, time_sec: float):
        """시간에 가장 가까운 캐시 프레임의 PIL Image 반환"""
        if not self._cached_frames:
            return None
        best = min(self._cached_frames, key=lambda x: abs(x[0] - time_sec))
        return best[1].copy()

    def _show_cached_frame(self, time_sec: float):
        """캐시에서 프레임 찾아 표시 (자막 합성 포함)"""
        img = self._find_nearest_frame(time_sec)
        if img is None:
            return
        self._set_preview_image(img)

    def _set_preview_image(self, img):
        """PIL Image → CTkLabel 표시 (자막 합성 포함)"""
        try:
            from PIL import Image as _PImg

            # 자막 합성
            img = self._draw_subtitles_on_frame(img, self._preview_current_time)

            # 라벨 크기에 맞춰 조정
            w = self._preview_label.winfo_width()
            h = self._preview_label.winfo_height()
            if w < 50 or h < 50:
                w, h = 640, 270

            img.thumbnail((w - 4, h - 4), _PImg.LANCZOS)

            self._preview_photo = ctk.CTkImage(
                light_image=img, dark_image=img,
                size=(img.width, img.height),
            )
            self._preview_label.configure(image=self._preview_photo, text="")
        except Exception:
            pass

    def _draw_subtitles_on_frame(self, img, time_sec: float):
        """
        현재 시점에 활성화된 자막을 이미지에 렌더링.
        실제 변환 결과와 최대한 비슷하게 표시.
        """
        if not self._subtitles_data:
            return img

        try:
            from PIL import ImageDraw, ImageFont, Image as _PImg

            # 현재 시점에 표시될 자막들 필터링
            active_subs = [
                s for s in self._subtitles_data
                if s.start <= time_sec <= s.end and s.text.strip()
            ]

            if not active_subs:
                return img

            # RGB → RGBA 변환
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 직접 이미지 위에 그리기 (overlay 대신 — 더 안정적)
            # 반투명 배경은 별도 overlay 사용
            overlay = _PImg.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            for sub in active_subs:
                # 480p 기준 정규화
                preview_size = max(14, int(sub.size * img.height / 480))

                # 폰트 로드 (여러 경로 시도)
                font = None
                bold = getattr(sub, 'bold', True)
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
                text = sub.text
                bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=4)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                padding = max(6, int(preview_size * 0.3))

                # 위치 계산
                x = (img.width - tw) // 2
                if sub.position == "top":
                    y = int(img.height * 0.05)
                elif sub.position == "middle":
                    y = (img.height - th) // 2
                else:  # bottom
                    y = img.height - th - int(img.height * 0.05)

                # y 보정 (bbox[1]이 0이 아닐 수 있음)
                text_y = y - bbox[1]

                # 반투명 검정 배경 박스 (불투명도 높임)
                draw.rectangle(
                    [x - padding, y - padding, x + tw + padding, y + th + padding],
                    fill=(0, 0, 0, 180),
                )

                # 검정 테두리 (가독성)
                border = max(1, preview_size // 15)
                for dx in range(-border, border + 1):
                    for dy in range(-border, border + 1):
                        if dx == 0 and dy == 0:
                            continue
                        draw.multiline_text(
                            (x + dx, text_y + dy), text,
                            fill=(0, 0, 0, 255), font=font, spacing=4, align="center",
                        )

                # 자막 색상
                color = _hex_to_rgba(sub.color)
                draw.multiline_text(
                    (x, text_y), text,
                    fill=color, font=font, spacing=4, align="center",
                )

            # 합성 후 RGB로 변환 (CTkImage 호환)
            result = _PImg_alpha_composite(img, overlay)
            overlay.close()
            return result.convert('RGB')

        except Exception:
            return img

    def _on_preview_slider(self, val):
        """미리보기 슬라이더 이동 → 캐시에서 즉시 프레임 표시"""
        if not self._video_info:
            return
        v = float(val)
        self._preview_current_time = v
        self._update_preview_time_label()

        # 캐시에서 즉시 표시 (디바운스 불필요)
        self._show_cached_frame(v)

    def _update_preview_time_label(self):
        dur = self._video_info.duration if self._video_info else 0
        self._preview_time_label.configure(
            text=f"{self._preview_current_time:.1f} / {dur:.1f}s"
        )

    def _toggle_play(self):
        if not self._video_info:
            return
        if not self._cached_frames:
            self._status_label.configure(
                text="⏳ 미리보기 준비 중이에요 — 잠시 후 다시 눌러주세요 (구간은 슬라이더로 바로 지정 가능)",
                text_color="#f59e0b")
            return
        if self._preview_playing:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self):
        self._preview_playing = True
        self._play_btn.configure(text="⏸ 정지")
        # 현재 위치에서 가장 가까운 캐시 프레임부터 시작
        cur = self._preview_current_time
        self._play_idx = min(range(len(self._cached_frames)),
                             key=lambda i: abs(self._cached_frames[i][0] - cur))
        self._play_next_frame()

    def _stop_play(self):
        self._preview_playing = False
        self._play_btn.configure(text="▶ 재생")
        if self._preview_after_id:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None

    def _play_next_frame(self):
        """재생 루프: 캐시 프레임을 고정 ~12fps로 표시 (캐시가 듬성해도 항상 부드럽게, 끝나면 루프)"""
        if not self._preview_playing or not self._cached_frames:
            return

        n = len(self._cached_frames)
        idx = getattr(self, "_play_idx", 0) % n
        t = self._cached_frames[idx][0]

        self._preview_current_time = t
        try:
            self._preview_slider.set(t)
        except Exception:
            pass
        self._update_preview_time_label()
        self._show_cached_frame(t)

        self._play_idx = (idx + 1) % n  # 끝 → 처음 (루프)
        self._preview_after_id = self.after(80, self._play_next_frame)

    def _mark_start(self):
        """현재 미리보기 시점을 시작으로 지정"""
        if not self._video_info:
            return
        t = self._preview_current_time
        self._start_slider.set(t)
        self._start_entry.delete(0, "end")
        self._start_entry.insert(0, f"{t:.1f}")
        # 시작이 끝보다 크면 끝도 조정
        end_val = self._get_end()
        if end_val > 0 and t >= end_val:
            new_end = min(t + 3, self._video_info.duration)
            self._end_slider.set(new_end)
            self._end_entry.delete(0, "end")
            self._end_entry.insert(0, f"{new_end:.1f}")
        self._update_duration_label()
        self._update_warn()
        self._update_estimate()

    def _mark_end(self):
        """현재 미리보기 시점을 끝으로 지정"""
        if not self._video_info:
            return
        t = self._preview_current_time
        self._end_slider.set(t)
        self._end_entry.delete(0, "end")
        self._end_entry.insert(0, f"{t:.1f}")
        # 끝이 시작보다 작으면 시작도 조정
        start_val = self._get_start()
        if t <= start_val:
            new_start = max(0, t - 3)
            self._start_slider.set(new_start)
            self._start_entry.delete(0, "end")
            self._start_entry.insert(0, f"{new_start:.1f}")
        self._update_duration_label()
        self._update_warn()
        self._update_estimate()

    # ════════════════════════════════════════
    # ✂️ 자동 분할 관리
    # ════════════════════════════════════════
    def _on_split_toggle(self):
        """분할 체크박스 on/off"""
        if self._split_var.get():
            self._split_settings.pack(fill="x", padx=8, pady=(0, 8))
            self._update_split_preview()
        else:
            self._split_settings.pack_forget()

    def _on_split_mode_change(self):
        """분할 방식 변경 (개수 / 시간)"""
        if self._split_mode_var.get() == "count":
            self._split_quick_frame.pack(fill="x", pady=2)
            self._split_dur_frame.pack_forget()
        else:
            self._split_quick_frame.pack_forget()
            self._split_dur_frame.pack(fill="x", pady=2)
        self._update_split_preview()

    def _set_split_count(self, n: int):
        """빠른 선택 버튼"""
        self._split_count_entry.delete(0, "end")
        self._split_count_entry.insert(0, str(n))
        self._update_split_preview()

    def _update_split_preview(self):
        """분할 예상 결과 계산 + 표시"""
        if not self._video_info:
            self._split_preview_label.configure(text="영상을 먼저 열어주세요")
            return

        segments = self._calculate_split_segments()
        if not segments:
            self._split_preview_label.configure(text="⚠ 분할 설정을 확인하세요")
            return

        total_dur = self._video_info.duration
        n = len(segments)
        each_dur = segments[0][1] - segments[0][0]

        text = f"📋 {total_dur:.0f}초 영상 → 각 {each_dur:.1f}초씩 {n}개 생성"
        self._split_preview_label.configure(text=text)

    def _calculate_split_segments(self):
        """
        분할 구간 리스트 반환: [(start, end), (start, end), ...]
        구간 설정이 있으면 그 안에서만 분할.
        """
        if not self._video_info:
            return []

        # 전체 구간 또는 사용자 설정 구간
        clip_start = self._get_start()
        clip_end = self._get_end()
        if clip_end <= 0:
            clip_end = self._video_info.duration
        total = clip_end - clip_start

        if total <= 0:
            return []

        # 겹치기
        try:
            overlap = float(self._split_overlap_entry.get() or 0)
        except ValueError:
            overlap = 0
        overlap = max(0, min(overlap, total / 2))  # 너무 크면 제한

        mode = self._split_mode_var.get()

        if mode == "count":
            try:
                n = int(self._split_count_entry.get() or 5)
            except ValueError:
                n = 5
            n = max(1, min(n, 100))

            if n == 1:
                return [(clip_start, clip_end)]

            # 유효 구간 = 전체 - 겹침 합계
            effective = total + overlap * (n - 1)
            each = effective / n

        else:  # duration
            try:
                each = float(self._split_dur_entry.get() or 10)
            except ValueError:
                each = 10
            each = max(1, each)
            n = max(1, int((total + overlap * 0.999) / (each - overlap)))

        # 구간 생성
        segments = []
        for i in range(n):
            s = clip_start + i * (each - overlap)
            e = min(s + each, clip_end + overlap)
            e = min(e, self._video_info.duration)  # 영상 끝 초과 방지
            if s >= self._video_info.duration:
                break
            segments.append((round(s, 3), round(e, 3)))

        return segments

    # ════════════════════════════════════════
    # 💬 자막 관리
    # ════════════════════════════════════════
    def _add_subtitle(self):
        """자막 입력값을 목록에 추가 + 미리보기 갱신"""
        # CTkTextbox에서 텍스트 가져오기 (끝 줄바꿈 제거)
        text = self._sub_text_entry.get("1.0", "end-1c").strip()
        if not text:
            return

        try:
            start = float(self._sub_start_entry.get() or 0)
            end_raw = self._sub_end_entry.get().strip()
            if not end_raw:
                end = start + 3
            else:
                end = float(end_raw)
        except ValueError:
            return

        if end <= start:
            end = start + 3

        # 위치 한글→영어 매핑
        pos_map = {"하단": "bottom", "중앙": "middle", "상단": "top"}
        position = pos_map.get(self._sub_pos_var.get(), "bottom")

        sub = Subtitle(
            text=text, start=start, end=end,
            position=position,
            size=self._sub_size_var.get(),
            color=self._get_sub_color(),
            bold=self._sub_bold_var.get(),
        )
        self._subtitles_data.append(sub)
        self._refresh_sub_list()

        # 입력 필드 초기화 (Textbox는 delete 방식 다름)
        self._sub_text_entry.delete("1.0", "end")
        self._sub_start_entry.delete(0, "end")
        self._sub_end_entry.delete(0, "end")

        # 미리보기: 자막 시작 시점으로 점프 + 즉시 갱신
        if self._video_info:
            self._preview_current_time = start
            self._preview_slider.set(start)
            self._update_preview_time_label()
            self._show_cached_frame(start)

    def _clear_subtitles(self):
        self._subtitles_data.clear()
        self._refresh_sub_list()
        # 미리보기 갱신 (자막 사라짐 반영)
        if self._video_info:
            self._show_cached_frame(self._preview_current_time)

    def _refresh_sub_list(self):
        """자막 목록 UI 갱신 (개별 삭제 버튼 포함)"""
        # 기존 위젯 정리
        for widget in self._sub_list_frame.winfo_children():
            widget.destroy()

        if not self._subtitles_data:
            self._sub_empty_label = ctk.CTkLabel(
                self._sub_list_frame, text="(자막 없음)",
                font=ctk.CTkFont(size=11), text_color="gray50",
                anchor="w",
            )
            self._sub_empty_label.pack(fill="x")
            return

        pos_kr = {"bottom": "하단", "middle": "중앙", "top": "상단"}
        for i, sub in enumerate(self._subtitles_data):
            row = ctk.CTkFrame(self._sub_list_frame, fg_color="gray25", corner_radius=4, height=26)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            # 자막 정보 텍스트
            first_line = sub.text.split("\n")[0]
            txt = first_line[:18] + "…" if len(first_line) > 18 else first_line
            pos = pos_kr.get(sub.position, sub.position)
            info = f"{i+1}. [{sub.start:.0f}~{sub.end:.0f}s] {pos} {txt}"

            ctk.CTkLabel(
                row, text=info,
                font=ctk.CTkFont(size=10),
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=4)

            # ✕ 삭제 버튼
            ctk.CTkButton(
                row, text="✕", width=22, height=20,
                font=ctk.CTkFont(size=10),
                fg_color="#dc2626", hover_color="#b91c1c",
                command=lambda idx=i: self._delete_subtitle(idx),
            ).pack(side="right", padx=2)

    def _delete_subtitle(self, index: int):
        """자막 개별 삭제"""
        if 0 <= index < len(self._subtitles_data):
            self._subtitles_data.pop(index)
            self._refresh_sub_list()
            # 미리보기 갱신
            if self._video_info:
                self._show_cached_frame(self._preview_current_time)

    # 자막 색상 매핑
    _COLOR_MAP = {
        "⬜ 흰색": "#FFFFFF",
        "🟨 노랑": "#FFFF00",
        "🟥 빨강": "#FF0000",
        "🟩 초록": "#00FF00",
        "🟦 파랑": "#00BFFF",
        "⬛ 검정": "#000000",
    }

    def _get_sub_color(self) -> str:
        """선택된 자막 색상을 hex로 변환"""
        return self._COLOR_MAP.get(self._sub_color_var.get(), "#FFFFFF")

    def _update_color_preview(self):
        """색상 미리보기 라벨 업데이트"""
        hex_color = self._get_sub_color()
        self._sub_color_preview.configure(text_color=hex_color)



    def _auto_tune_settings(self, info: VideoInfo):
        """
        영상 속성 + 가용 RAM 기반으로 안전한 설정 자동 적용.
        목표: 어떤 영상이든 절대 컴퓨터 안 멈추게.
        """
        try:
            import psutil
            available_ram_mb = psutil.virtual_memory().available // (1024 * 1024)
        except ImportError:
            available_ram_mb = 4096  # psutil 없으면 4GB 가정

        duration = info.duration
        src_w = info.width
        src_fps = info.fps

        # ── 1. 해상도 자동 결정 ──
        # RAM 여유가 충분하고 원본이 작으면 원본 유지
        # 아니면 자동 다운스케일
        if src_w <= 854:  # 480p 이하 원본
            target_res = "원본"
            target_w = src_w
        elif src_w <= 1280 and available_ram_mb > 8000 and duration < 30:
            target_res = "720p"
            target_w = 1280
        elif src_w <= 1920 and available_ram_mb > 4000 and duration < 15:
            target_res = "720p"
            target_w = 1280
        else:
            # HD 이상 원본 또는 RAM 부족 → 480p
            target_res = "480p"
            target_w = 854

        self._res_var.set(target_res)
        self._on_res_change()

        # ── 2. FPS 자동 결정 ──
        # 픽셀 × 프레임 수가 너무 크면 FPS 낮춤
        total_pixels = target_w * (target_w * 9 // 16) * duration
        if total_pixels > 200_000_000:  # 2억 픽셀 이상
            target_fps = "10"
        elif total_pixels > 100_000_000:
            target_fps = "12"
        elif src_fps >= 24:
            target_fps = "15"
        else:
            target_fps = "15"

        self._fps_var.set(target_fps)

        # ── 3. 30초 이상이면 자동으로 구간 제한 제안 ──
        if duration > 30:
            # 끝 슬라이더를 30초로 이동
            self._end_slider.set(30)
            self._on_end_slider(30)
            self._status_label.configure(
                text=f"🎯 자동 설정: {target_res}, {target_fps}fps, 30초 구간 (길어서 자름)",
                text_color="#3b82f6",
            )
        else:
            self._status_label.configure(
                text=f"🎯 자동 설정 완료: {target_res}, {target_fps}fps (RAM {available_ram_mb}MB 고려)",
                text_color="#3b82f6",
            )

    def add_file_from_drop(self, path: str):
        """드래그앤드롭으로 파일 받기"""
        if is_video_file(path):
            self._video_path = path
            self._cleanup_cache()
            name = Path(path).name
            if len(name) > 40:
                name = name[:37] + "..."
            self._file_label.configure(text=name, text_color="white")
            threading.Thread(target=self._probe_video, daemon=True).start()

    # ════════════════════════════════════════
    # 설정 콜백
    # ════════════════════════════════════════
    def _on_start_slider(self, val):
        if self._video_info:
            self._start_entry.delete(0, "end")
            self._start_entry.insert(0, f"{float(val):.1f}")
            # 시작이 끝보다 크면 끝을 밀어줌
            end_val = self._get_end()
            if end_val > 0 and float(val) >= end_val:
                self._end_slider.set(min(float(val) + 1, self._video_info.duration))
                self._on_end_slider(self._end_slider.get())
            self._update_duration_label()
        self._update_warn()
        self._update_estimate()

    def _on_end_slider(self, val):
        if self._video_info:
            self._end_entry.delete(0, "end")
            v = float(val)
            if v >= self._video_info.duration - 0.5:
                self._end_entry.configure(placeholder_text=f"{self._video_info.duration:.1f}")
            else:
                self._end_entry.insert(0, f"{v:.1f}")
            # 끝이 시작보다 작으면 시작을 당겨줌
            start_val = self._get_start()
            if v <= start_val and v > 0:
                self._start_slider.set(max(0, v - 1))
                self._on_start_slider(self._start_slider.get())
            self._update_duration_label()
        self._update_warn()
        self._update_estimate()

    def _update_duration_label(self):
        start = self._get_start()
        end = self._get_end()
        end_str = f"{end:.1f}초" if end > 0 else "끝"
        dur = (end if end > 0 else (self._video_info.duration if self._video_info else 0)) - start
        self._duration_label.configure(text=f"구간: {start:.1f}초 ~ {end_str} ({dur:.1f}초)")

    def _on_settings_change(self, val=None):
        self._quality_label.configure(text=f"{self._quality_var.get()}%")
        self._update_warn()
        self._update_estimate()

    def _update_warn(self):
        """포맷 + 구간 길이 + 해상도에 따른 경고 표시"""
        if not self._video_info:
            self._warn_label.configure(text="")
            return
        start = self._get_start()
        end = self._get_end()
        dur = (end if end > 0 else self._video_info.duration) - start
        fmt = self._format_var.get()
        res = self._res_var.get()

        warnings = []

        # 고해상도 + 원본 유지 경고 (메모리 폭주 방지)
        if res == "원본" and self._video_info.width >= 1280:
            warnings.append("⚠ HD 이상 원본 크기는 메모리를 많이 씁니다 → 해상도 낮추길 권장")

        if fmt == "gif" and dur > 30:
            warnings.append("⚠ GIF 30초 이상은 용량이 매우 큽니다. 구간을 잘라주세요.")
        elif fmt == "apng" and dur > 15:
            warnings.append("⚠ APNG는 무손실이라 긴 영상은 용량이 클 수 있습니다.")

        self._warn_label.configure(text=" / ".join(warnings))

    def _on_safe_mode_toggle(self):
        """안전 모드 on/off 시 즉시 재튜닝"""
        if self._safe_mode_var.get() and self._video_info:
            self._auto_tune_settings(self._video_info)

    def _on_res_change(self, val=None):
        if "커스텀" in self._res_var.get():
            self._custom_w_frame.grid()
        else:
            self._custom_w_frame.grid_remove()
        self._update_estimate()

    def _on_optimize_toggle(self):
        if self._optimize_var.get():
            self._target_frame.grid()
        else:
            self._target_frame.grid_remove()

    def _browse_output(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(initialdir=self._output_dir.get())
        if d:
            self._output_dir.set(d)
            settings.set("output_dir", d)
            settings.save()

    def _update_estimate(self):
        if not self._video_info:
            self._est_label.configure(text="예상 용량: -")
            return
        fps = self._get_fps()
        width = self._get_width()
        start = self._get_start()
        end = self._get_end()
        speed = self._get_speed()
        est = estimate_video_output_size(
            self._video_info, self._format_var.get(),
            fps, width, self._quality_var.get(),
            start, end, speed,
        )
        self._est_label.configure(text=f"예상 용량: ~{format_filesize(est)}")

    # ════════════════════════════════════════
    # 값 파싱 헬퍼
    # ════════════════════════════════════════
    def _get_fps(self) -> int:
        val = self._fps_var.get()
        if "원본" in val:
            return int(self._video_info.fps) if self._video_info else 15
        try:
            return int(val)
        except ValueError:
            return 15

    def _get_width(self) -> int:
        val = self._res_var.get()
        res_map = {"720p": 1280, "480p": 854, "360p": 640, "240p": 426}
        if val in res_map:
            return res_map[val]
        if "커스텀" in val:
            try:
                return max(100, int(self._custom_w_entry.get()))
            except ValueError:
                return 480
        return 0  # 원본

    def _get_start(self) -> float:
        try:
            return max(0, float(self._start_entry.get()))
        except ValueError:
            return 0.0

    def _get_end(self) -> float:
        # entry에 직접 입력한 값 우선
        text = self._end_entry.get().strip()
        if text:
            try:
                return float(text)
            except ValueError:
                pass
        # entry 비어있으면 슬라이더 값 사용
        if self._video_info:
            slider_val = float(self._end_slider.get())
            # 슬라이더가 끝까지 당겨져 있으면 0 (= 끝까지)
            if slider_val >= self._video_info.duration - 0.5:
                return 0.0
            return slider_val
        return 0.0  # 0 = 끝까지

    def _get_speed(self) -> float:
        try:
            return float(self._speed_var.get().replace("x", ""))
        except ValueError:
            return 1.0

    def _get_loop(self) -> int:
        val = self._loop_var.get()
        if "무한" in val:
            return 0
        try:
            return int(val.replace("회", ""))
        except ValueError:
            return 0

    # ════════════════════════════════════════
    # 변환 실행
    # ════════════════════════════════════════
    def _build_job(self) -> ConvertJob:
        job = ConvertJob()
        job.input_path = self._video_path
        job.output_format = self._format_var.get()
        job.start_time = self._get_start()
        job.end_time = self._get_end()
        job.fps = self._get_fps()
        job.width = self._get_width()
        job.quality = self._quality_var.get()
        _qm = self._qmode_var.get()
        job.quality_mode = "best" if "최고" in _qm else "fast" if "빠른" in _qm else "balanced"
        if job.quality_mode == "fast":
            job.fps = min(job.fps, 15)        # 빠른로딩: fps 상한 → 용량↓
            job.gif_lossy = 60
        elif job.quality_mode == "balanced":
            job.gif_lossy = 30
        else:
            job.gif_lossy = 0
        job.speed = self._get_speed()
        job.loop = self._get_loop()
        job.subtitles = list(self._subtitles_data)  # 자막 복사

        # 출력 높이 계산 (자막 크기 정규화용)
        if self._video_info and job.width > 0:
            ratio = self._video_info.height / max(1, self._video_info.width)
            job.output_height = max(1, int(job.width * ratio))
        elif self._video_info:
            job.output_height = self._video_info.height
        else:
            job.output_height = 480

        ext = "apng" if job.output_format == "apng" else job.output_format
        base_name = Path(self._video_path).stem
        job.output_path = generate_output_name(base_name, ext, self._output_dir.get())
        return job

    def _start_convert(self):
        if self._working:
            return
        if not self._video_path or not Path(self._video_path).exists():
            self._status_label.configure(text="⚠ 영상 파일을 먼저 선택하세요", text_color="#f59e0b")
            return
        if not ffmpeg_available():
            self._status_label.configure(text="⚠ FFmpeg가 필요합니다", text_color="#ef4444")
            return

        # ── 🛡️ 안전 모드 ──
        if self._safe_mode_var.get() and self._video_info:
            if not self._safety_check_ok():
                return

        self._working = True
        self._convert_btn.grid_remove()
        self._cancel_btn.grid()
        self._progress.set(0)

        settings.set("video_output_format", self._format_var.get())
        settings.set("video_quality", self._quality_var.get())
        settings.set("video_quality_mode", self._qmode_var.get())
        settings.save()

        # ── ✂️ 분할 모드 체크 ──
        if self._split_var.get():
            segments = self._calculate_split_segments()
            if not segments or len(segments) < 2:
                self._status_label.configure(text="⚠ 분할 설정을 확인하세요 (2개 이상)", text_color="#f59e0b")
                self._working = False
                self._cancel_btn.grid_remove()
                self._convert_btn.grid()
                return
            self._status_label.configure(
                text=f"✂️ {len(segments)}개로 분할 변환 시작...", text_color="white",
            )
            threading.Thread(
                target=self._run_split_convert, args=(segments,), daemon=True,
            ).start()
        else:
            self._job = self._build_job()
            self._status_label.configure(text="변환 시작...", text_color="white")
            threading.Thread(target=self._run_convert, daemon=True).start()

    def _safety_check_ok(self) -> bool:
        """
        변환 시작 전 RAM 여유 체크 → 위험하면 자동 다운스케일.
        반환: True (진행 OK) / False (취소됨)
        """
        try:
            import psutil
            available_mb = psutil.virtual_memory().available // (1024 * 1024)
        except ImportError:
            available_mb = 4096

        w = self._get_width() or self._video_info.width
        h_ratio = self._video_info.height / max(1, self._video_info.width)
        h = int(w * h_ratio)
        fps = self._get_fps()
        dur = (self._get_end() if self._get_end() > 0 else self._video_info.duration) - self._get_start()

        # 예상 RAM 사용량: 프레임당 w×h×4바이트 × FFmpeg 버퍼 ~3배
        frame_bytes = w * h * 4
        estimated_peak_mb = (frame_bytes * fps * min(dur, 10) * 3) // (1024 * 1024)

        # 가용 RAM의 30% 이하만 쓰도록
        safe_limit = available_mb // 3

        if estimated_peak_mb > safe_limit:
            # 자동 다운스케일 제안
            self._status_label.configure(
                text=f"🛡️ 현재 설정은 RAM {estimated_peak_mb}MB 필요 (가용 {available_mb}MB). 자동으로 낮춥니다...",
                text_color="#f59e0b",
            )
            # 해상도를 한 단계 낮춤
            current_res = self._res_var.get()
            res_order = ["720p", "480p", "360p", "240p"]
            if current_res == "원본":
                self._res_var.set("720p")
            elif current_res in res_order:
                idx = res_order.index(current_res)
                if idx < len(res_order) - 1:
                    self._res_var.set(res_order[idx + 1])
            self._on_res_change()
            # FPS도 낮춤
            self._fps_var.set("10")
            self._update_estimate()
            # 재귀 호출 (또 위험하면 또 낮춤)
            return self._safety_check_ok()

        return True

    def _run_convert(self):
        def on_progress(pct, msg):
            self.after(0, lambda p=pct, m=msg: self._update_progress(p, m))

        result = convert_video(self._job, on_progress=on_progress)

        # 최적화 옵션
        if result and self._optimize_var.get():
            result = self._apply_optimize(result)

        self.after(0, lambda: self._on_convert_done(result))

    def _run_split_convert(self, segments):
        """분할 모드: 각 구간별 순차 변환"""
        total = len(segments)
        completed = []
        base_job = self._build_job()

        for idx, (seg_start, seg_end) in enumerate(segments):
            # 취소 체크
            if base_job.cancelled:
                break

            part_num = idx + 1

            def on_progress(pct, msg, _n=part_num, _t=total):
                # 전체 진행률: 각 클립 진행률을 전체에 매핑
                overall = int(((_n - 1) / _t) * 100 + (pct / _t))
                overall_msg = f"✂️ {_n}/{_t} 변환 중 ({pct}%) — {msg}"
                self.after(0, lambda p=overall, m=overall_msg: self._update_progress(p, m))

            # 각 분할용 job 생성
            job = ConvertJob()
            job.input_path = base_job.input_path
            job.output_format = base_job.output_format
            job.start_time = seg_start
            job.end_time = seg_end
            job.fps = base_job.fps
            job.width = base_job.width
            job.height = base_job.height
            job.quality = base_job.quality
            job.quality_mode = base_job.quality_mode
            job.gif_lossy = base_job.gif_lossy
            job.speed = base_job.speed
            job.loop = base_job.loop
            job.output_height = base_job.output_height

            # 자막 처리
            if self._split_sub_var.get() and base_job.subtitles:
                # "모든 분할에 자막 적용" → 각 구간 전체에 자막 표시
                adjusted_subs = []
                for orig_sub in base_job.subtitles:
                    sub_copy = Subtitle(
                        text=orig_sub.text,
                        start=seg_start,  # 구간 시작에 맞춤
                        end=seg_end,      # 구간 끝에 맞춤
                        position=orig_sub.position,
                        size=orig_sub.size,
                        color=orig_sub.color,
                        bold=orig_sub.bold,
                    )
                    adjusted_subs.append(sub_copy)
                job.subtitles = adjusted_subs
            else:
                job.subtitles = base_job.subtitles  # 원본 시간 기준

            # 출력 파일명: 영상명_part1.gif, _part2.gif, ...
            ext = "apng" if job.output_format == "apng" else job.output_format
            base_name = Path(base_job.input_path).stem
            part_name = f"{base_name}_part{part_num}"
            job.output_path = generate_output_name(part_name, ext, self._output_dir.get())

            # 취소 연결
            self._job = job

            result = convert_video(job, on_progress=on_progress)

            if result and Path(result).exists():
                # 최적화
                if self._optimize_var.get():
                    result = self._apply_optimize(result)
                completed.append(result)
            else:
                if job.cancelled:
                    break

        # 완료 처리
        self.after(0, lambda: self._on_split_done(completed, total))

    def _apply_optimize(self, result):
        """변환 결과물에 최적화 적용 (분할/일반 공용)"""
        try:
            target_kb = int(self._target_kb_entry.get())
        except ValueError:
            target_kb = 5000

        current_kb = Path(result).stat().st_size // 1024
        if current_kb <= target_kb:
            return result

        def opt_cb(msg):
            self.after(0, lambda m=msg: self._status_label.configure(text=f"🎯 {m}"))

        optimized = auto_optimize(result, target_kb, on_progress=opt_cb)
        if optimized and optimized != result:
            try:
                import shutil
                shutil.copy2(optimized, result)
                Path(optimized).unlink(missing_ok=True)
            except Exception:
                result = optimized

        return result

    def _on_split_done(self, completed, total):
        """분할 변환 완료 처리"""
        self._working = False
        self._cancel_btn.grid_remove()
        self._convert_btn.grid()

        if completed:
            total_size = sum(Path(f).stat().st_size for f in completed if Path(f).exists())
            size_str = format_filesize(total_size)
            self._status_label.configure(
                text=f"✅ 분할 완료! {len(completed)}/{total}개 생성 (총 {size_str})",
                text_color="#22c55e",
            )
            self._progress.set(1.0)
            self._show_open_folder(str(Path(completed[0]).parent))
        else:
            self._progress.set(0)
            if self._job and self._job.cancelled:
                self._status_label.configure(text="⏹ 취소됨", text_color="#f59e0b")
            else:
                self._status_label.configure(text="❌ 분할 변환 실패", text_color="#ef4444")

    def _update_progress(self, pct: int, msg: str):
        self._progress.set(pct / 100)
        self._status_label.configure(text=msg)

    def _on_convert_done(self, result):
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
            self._show_open_folder(str(Path(result).parent))
        else:
            self._progress.set(0)
            if self._job and self._job.cancelled:
                self._status_label.configure(text="⏹ 취소됨", text_color="#f59e0b")
            else:
                self._status_label.configure(text="❌ 변환 실패", text_color="#ef4444")

    def _cancel_convert(self):
        if self._job:
            self._job.cancelled = True
        self._status_label.configure(text="취소 중...", text_color="#f59e0b")

    def _show_open_folder(self, folder: str):
        import subprocess as _sp
        import sys as _sys

        if hasattr(self, '_open_folder_btn') and self._open_folder_btn:
            try:
                self._open_folder_btn.destroy()
            except Exception:
                pass

        def open_it():
            try:
                if _sys.platform == "win32":
                    os.startfile(folder)
                elif _sys.platform == "darwin":
                    _sp.Popen(["open", folder])
                else:
                    _sp.Popen(["xdg-open", folder])
            except Exception:
                pass

        self._open_folder_btn = ctk.CTkButton(
            self._status_label.master,
            text="📂 출력 폴더 열기", height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#16a34a", hover_color="#15803d",
            command=open_it,
        )
        self._open_folder_btn.grid(row=10, column=0, sticky="ew", padx=12, pady=(4, 8))
