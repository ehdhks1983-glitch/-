"""
ui_shorts_tab.py - 쇼츠 제작 탭 UI
사진을 장면으로 추가 → 장면별 템플릿/자막/나래이션 → 배경음악 → 세로 9:16 MP4
"""

import os
import threading
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
from PIL import Image

from config import settings
from utils import generate_output_name, is_image_file, IMAGE_EXTS
from shorts_maker import (
    ShortsProject, ShortsSegment, build_shorts, render_segment_frame,
)

TEMPLATE_NAMES = {"blur": "흐림 배경", "fill": "꽉 채움", "card": "카드뉴스"}
NAME_TO_TEMPLATE = {v: k for k, v in TEMPLATE_NAMES.items()}


class ShortsTab(ctk.CTkFrame):
    """쇼츠 제작 탭"""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._segments: List[ShortsSegment] = []
        self._selected: Optional[int] = None
        self._working: bool = False
        self._bgm_path: str = ""
        self._preview_img = None
        self._open_folder_btn = None
        self._row_widgets: list = []
        self._build_ui()

    # ════════════════════════════════════════
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1, minsize=300)  # 좌: 장면 목록 + 미리보기
        self.grid_columnconfigure(1, weight=1, minsize=320)  # 우: 편집 설정
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()

    # ─── 좌측: 장면 목록 + 미리보기 ───
    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color="gray14", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(left, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(header, text="🎬 장면 목록",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="➕ 사진 추가", width=100, height=28,
                      font=ctk.CTkFont(size=12), command=self._add_photos).pack(side="right", padx=2)

        ord_frame = ctk.CTkFrame(left, fg_color="transparent")
        ord_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        ctk.CTkButton(ord_frame, text="🔼", width=40, height=26, fg_color="gray30",
                      command=lambda: self._move(-1)).pack(side="left", padx=2)
        ctk.CTkButton(ord_frame, text="🔽", width=40, height=26, fg_color="gray30",
                      command=lambda: self._move(1)).pack(side="left", padx=2)
        ctk.CTkButton(ord_frame, text="🗑 전체삭제", width=90, height=26, fg_color="gray30",
                      hover_color="#cc4444", command=self._clear_all).pack(side="right", padx=2)
        self._count_label = ctk.CTkLabel(ord_frame, text="0개", font=ctk.CTkFont(size=12),
                                          text_color="gray50")
        self._count_label.pack(side="right", padx=8)

        self._list_scroll = ctk.CTkScrollableFrame(left, fg_color="gray17", corner_radius=6,
                                                   height=180)
        self._list_scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self._empty_label = ctk.CTkLabel(
            self._list_scroll, text="'➕ 사진 추가'로\n장면을 만들어 주세요",
            font=ctk.CTkFont(size=13), text_color="gray50")
        self._empty_label.pack(expand=True, pady=40)

        # 미리보기
        ctk.CTkLabel(left, text="미리보기 (선택한 장면)",
                     font=ctk.CTkFont(size=12), text_color="gray50").grid(
            row=3, column=0, sticky="w", padx=12, pady=(6, 0))
        self._preview_label = ctk.CTkLabel(left, text="세로 9:16", height=300,
                                           font=ctk.CTkFont(size=14), text_color="gray40")
        self._preview_label.grid(row=4, column=0, sticky="nsew", padx=12, pady=(2, 12))

    # ─── 우측: 편집 + 빌드 ───
    def _build_right(self):
        right = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)
        pad = {"padx": 12, "pady": (4, 2), "sticky": "ew"}

        # ── 선택한 장면 편집 ──
        ctk.CTkLabel(right, text="✏️ 선택한 장면 편집",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, **pad)

        ctk.CTkLabel(right, text="구조(템플릿)", font=ctk.CTkFont(size=12)).grid(row=1, column=0, **pad)
        self._tpl_var = ctk.StringVar(value="흐림 배경")
        ctk.CTkOptionMenu(right, values=list(TEMPLATE_NAMES.values()), variable=self._tpl_var,
                          font=ctk.CTkFont(size=12), command=lambda _=None: self._apply_preview()
                          ).grid(row=2, column=0, **pad)

        ctk.CTkLabel(right, text="화면 자막", font=ctk.CTkFont(size=12)).grid(row=3, column=0, **pad)
        self._caption_box = ctk.CTkTextbox(right, height=50, font=ctk.CTkFont(size=12), wrap="word")
        self._caption_box.grid(row=4, column=0, **pad)

        ctk.CTkLabel(right, text="나래이션 (음성으로 읽을 글)",
                     font=ctk.CTkFont(size=12)).grid(row=5, column=0, **pad)
        self._narr_box = ctk.CTkTextbox(right, height=60, font=ctk.CTkFont(size=12), wrap="word")
        self._narr_box.grid(row=6, column=0, **pad)

        dur_frame = ctk.CTkFrame(right, fg_color="transparent")
        dur_frame.grid(row=7, column=0, **pad)
        ctk.CTkLabel(dur_frame, text="노출 시간", font=ctk.CTkFont(size=12)).pack(side="left")
        self._dur_var = ctk.DoubleVar(value=3.0)
        ctk.CTkSlider(dur_frame, from_=1, to=10, number_of_steps=18, variable=self._dur_var,
                      width=130, command=lambda _=None: self._dur_label.configure(
                          text=f"{self._dur_var.get():.1f}초")).pack(side="left", padx=8)
        self._dur_label = ctk.CTkLabel(dur_frame, text="3.0초", font=ctk.CTkFont(size=12), width=40)
        self._dur_label.pack(side="left")

        ctk.CTkButton(right, text="🔄 이 장면 적용 + 미리보기", height=32,
                      font=ctk.CTkFont(size=12), fg_color="#0ea5e9", hover_color="#0284c7",
                      command=self._apply_preview).grid(row=8, column=0, padx=12, pady=(4, 10), sticky="ew")

        # ── 배경음악 ──
        ctk.CTkLabel(right, text="🎵 배경음악 (선택)",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(row=9, column=0, **pad)
        bgm_frame = ctk.CTkFrame(right, fg_color="transparent")
        bgm_frame.grid(row=10, column=0, **pad)
        ctk.CTkButton(bgm_frame, text="🎵 음악 선택", width=100, height=28,
                      font=ctk.CTkFont(size=12), command=self._pick_bgm).pack(side="left", padx=(0, 6))
        self._bgm_label = ctk.CTkLabel(bgm_frame, text="없음", font=ctk.CTkFont(size=11),
                                       text_color="gray50")
        self._bgm_label.pack(side="left", fill="x", expand=True)

        vol_frame = ctk.CTkFrame(right, fg_color="transparent")
        vol_frame.grid(row=11, column=0, **pad)
        ctk.CTkLabel(vol_frame, text="음악 볼륨", font=ctk.CTkFont(size=12)).pack(side="left")
        self._vol_var = ctk.IntVar(value=25)
        ctk.CTkSlider(vol_frame, from_=0, to=100, variable=self._vol_var, width=130,
                      command=lambda _=None: self._vol_label.configure(
                          text=f"{self._vol_var.get()}%")).pack(side="left", padx=8)
        self._vol_label = ctk.CTkLabel(vol_frame, text="25%", font=ctk.CTkFont(size=12), width=40)
        self._vol_label.pack(side="left")

        # ── 공통 ──
        ctk.CTkLabel(right, text="⚙️ 공통 설정",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(row=12, column=0, **pad)
        size_frame = ctk.CTkFrame(right, fg_color="transparent")
        size_frame.grid(row=13, column=0, **pad)
        ctk.CTkLabel(size_frame, text="자막 크기", font=ctk.CTkFont(size=12)).pack(side="left")
        self._capsize_var = ctk.IntVar(value=56)
        ctk.CTkSlider(size_frame, from_=32, to=100, variable=self._capsize_var, width=130,
                      command=lambda _=None: self._apply_preview()).pack(side="left", padx=8)

        # ── 출력 폴더 ──
        ctk.CTkLabel(right, text="📂 출력 폴더",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=14, column=0, **pad)
        out_frame = ctk.CTkFrame(right, fg_color="transparent")
        out_frame.grid(row=15, column=0, **pad)
        self._output_dir = ctk.StringVar(value=settings.get("output_dir"))
        ctk.CTkEntry(out_frame, textvariable=self._output_dir, font=ctk.CTkFont(size=11),
                     height=28).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(out_frame, text="📁", width=30, height=28,
                      command=self._browse_output).pack(side="right")

        # ── 빌드 ──
        self._build_btn = ctk.CTkButton(
            right, text="🚀 쇼츠 만들기", height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#db2777", hover_color="#be185d", command=self._build)
        self._build_btn.grid(row=16, column=0, padx=12, pady=(10, 4), sticky="ew")

        self._progress = ctk.CTkProgressBar(right, height=14)
        self._progress.grid(row=17, column=0, padx=12, pady=4, sticky="ew")
        self._progress.set(0)
        self._status_label = ctk.CTkLabel(right, text="사진을 추가해 장면을 만들고, 자막·나래이션을 넣어보세요",
                                          font=ctk.CTkFont(size=11), text_color="gray50",
                                          wraplength=300, justify="left")
        self._status_label.grid(row=18, column=0, padx=12, pady=(0, 8), sticky="w")

    # ════════════════════════════════════════
    # 장면 관리
    # ════════════════════════════════════════
    def _add_photos(self):
        from tkinter import filedialog
        files = filedialog.askopenfilenames(
            title="사진 선택",
            filetypes=[("이미지", " ".join(f"*{e}" for e in IMAGE_EXTS)), ("모든 파일", "*.*")])
        if not files:
            return
        for f in files:
            if is_image_file(f):
                self._segments.append(ShortsSegment(image_path=f, duration=3.0, template="blur"))
        self._refresh_list()
        if self._selected is None and self._segments:
            self._select(len(self._segments) - len(files))

    def add_file_from_drop(self, path: str):
        if is_image_file(path):
            self._segments.append(ShortsSegment(image_path=path, duration=3.0, template="blur"))
            self._refresh_list()

    def _clear_all(self):
        self._segments.clear()
        self._selected = None
        self._refresh_list()
        self._preview_label.configure(image=None, text="세로 9:16")

    def _delete(self, idx: int):
        if 0 <= idx < len(self._segments):
            self._segments.pop(idx)
            if self._selected == idx:
                self._selected = None
            elif self._selected and self._selected > idx:
                self._selected -= 1
            self._refresh_list()

    def _move(self, direction: int):
        if self._selected is None:
            return
        i = self._selected
        j = i + direction
        if 0 <= j < len(self._segments):
            self._sync_editor_to_segment()
            self._segments[i], self._segments[j] = self._segments[j], self._segments[i]
            self._selected = j
            self._refresh_list()

    def _refresh_list(self):
        for w in self._list_scroll.winfo_children():
            w.destroy()
        self._row_widgets = []
        if not self._segments:
            self._empty_label = ctk.CTkLabel(
                self._list_scroll, text="'➕ 사진 추가'로\n장면을 만들어 주세요",
                font=ctk.CTkFont(size=13), text_color="gray50")
            self._empty_label.pack(expand=True, pady=40)
            self._count_label.configure(text="0개")
            return
        for i, seg in enumerate(self._segments):
            bg = "#1e3a5f" if self._selected == i else "gray20"
            row = ctk.CTkFrame(self._list_scroll, fg_color=bg, corner_radius=6, height=44)
            row.pack(fill="x", pady=2, padx=2)
            row.pack_propagate(False)
            cap = (seg.caption.split("\n")[0] or "(자막 없음)")[:14]
            label = ctk.CTkLabel(
                row, text=f"#{i+1}  [{TEMPLATE_NAMES.get(seg.template,'')}]  {cap}",
                font=ctk.CTkFont(size=12), anchor="w")
            label.pack(side="left", fill="x", expand=True, padx=8)
            ctk.CTkButton(row, text="✕", width=28, height=28, fg_color="gray30",
                          hover_color="#cc4444", font=ctk.CTkFont(size=13),
                          command=lambda idx=i: self._delete(idx)).pack(side="right", padx=6)
            for w in (row, label):
                w.bind("<Button-1>", lambda e, idx=i: self._select(idx))
            self._row_widgets.append(row)
        self._count_label.configure(text=f"{len(self._segments)}개")

    # ════════════════════════════════════════
    # 선택 / 편집 동기화
    # ════════════════════════════════════════
    def _select(self, idx: int):
        if self._selected is not None and self._selected != idx:
            self._sync_editor_to_segment()
        self._selected = idx
        self._load_segment_to_editor(idx)
        self._refresh_list()
        self._update_preview()

    def _load_segment_to_editor(self, idx: int):
        if not (0 <= idx < len(self._segments)):
            return
        seg = self._segments[idx]
        self._tpl_var.set(TEMPLATE_NAMES.get(seg.template, "흐림 배경"))
        self._caption_box.delete("1.0", "end")
        self._caption_box.insert("1.0", seg.caption)
        self._narr_box.delete("1.0", "end")
        self._narr_box.insert("1.0", seg.narration)
        self._dur_var.set(seg.duration)
        self._dur_label.configure(text=f"{seg.duration:.1f}초")

    def _sync_editor_to_segment(self):
        if self._selected is None or not (0 <= self._selected < len(self._segments)):
            return
        seg = self._segments[self._selected]
        seg.template = NAME_TO_TEMPLATE.get(self._tpl_var.get(), "blur")
        seg.caption = self._caption_box.get("1.0", "end-1c")
        seg.narration = self._narr_box.get("1.0", "end-1c")
        seg.duration = round(self._dur_var.get(), 1)

    def _apply_preview(self):
        self._sync_editor_to_segment()
        self._refresh_list()
        self._update_preview()

    def _update_preview(self):
        if self._selected is None or not (0 <= self._selected < len(self._segments)):
            return
        try:
            seg = self._segments[self._selected]
            frame = render_segment_frame(seg, self._capsize_var.get())
            frame.thumbnail((260, 460), Image.LANCZOS)
            self._preview_img = ctk.CTkImage(light_image=frame, dark_image=frame,
                                             size=(frame.width, frame.height))
            self._preview_label.configure(image=self._preview_img, text="")
            frame.close()
        except Exception:
            self._preview_label.configure(image=None, text="미리보기 실패")

    # ════════════════════════════════════════
    # 배경음악 / 출력
    # ════════════════════════════════════════
    def _pick_bgm(self):
        from tkinter import filedialog
        f = filedialog.askopenfilename(
            title="배경음악 선택",
            filetypes=[("음악", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac"), ("모든 파일", "*.*")])
        if f:
            self._bgm_path = f
            name = Path(f).name
            self._bgm_label.configure(text=name if len(name) <= 24 else name[:21] + "...",
                                      text_color="white")

    def _browse_output(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(initialdir=self._output_dir.get())
        if d:
            self._output_dir.set(d)
            settings.set("output_dir", d)
            settings.save()

    # ════════════════════════════════════════
    # 빌드
    # ════════════════════════════════════════
    def _build(self):
        if self._working:
            return
        self._sync_editor_to_segment()
        if not self._segments:
            self._status_label.configure(text="⚠ 사진을 먼저 추가하세요", text_color="#f59e0b")
            return

        self._working = True
        self._build_btn.configure(state="disabled")
        self._progress.set(0)
        if self._open_folder_btn:
            try:
                self._open_folder_btn.destroy()
            except Exception:
                pass
            self._open_folder_btn = None
        self._status_label.configure(text="쇼츠 만드는 중...", text_color="white")
        threading.Thread(target=self._run_build, daemon=True).start()

    def _run_build(self):
        proj = ShortsProject()
        # 세그먼트 복사본 전달 (빌드 중 UI 수정 안전)
        for s in self._segments:
            proj.segments.append(ShortsSegment(
                image_path=s.image_path, duration=s.duration, caption=s.caption,
                narration=s.narration, template=s.template))
        proj.bgm_path = self._bgm_path
        proj.bgm_volume = self._vol_var.get() / 100.0
        proj.caption_size = self._capsize_var.get()
        proj.output_path = generate_output_name("shorts", "mp4", self._output_dir.get())

        def on_progress(pct, msg):
            self.after(0, lambda p=pct, m=msg: self._update_progress(p, m))

        result = build_shorts(proj, on_progress=on_progress)
        self.after(0, lambda: self._on_build_done(result))

    def _update_progress(self, pct: int, msg: str):
        self._progress.set(pct / 100)
        self._status_label.configure(text=msg)

    def _on_build_done(self, result: Optional[str]):
        self._working = False
        self._build_btn.configure(state="normal")
        if result and Path(result).exists():
            from utils import format_filesize
            size = format_filesize(Path(result).stat().st_size)
            self._progress.set(1.0)
            self._status_label.configure(text=f"✅ 완성! {Path(result).name} ({size})",
                                         text_color="#22c55e")
            self._show_open_folder(str(Path(result).parent))
        else:
            self._progress.set(0)
            self._status_label.configure(text="❌ 쇼츠 만들기 실패", text_color="#ef4444")

    def _show_open_folder(self, folder: str):
        import subprocess as _sp
        import sys as _sys
        if self._open_folder_btn:
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
            self._status_label.master, text="📂 출력 폴더 열기", height=32,
            font=ctk.CTkFont(size=12), fg_color="#16a34a", hover_color="#15803d",
            command=open_it)
        self._open_folder_btn.grid(row=19, column=0, padx=12, pady=(0, 8), sticky="ew")
