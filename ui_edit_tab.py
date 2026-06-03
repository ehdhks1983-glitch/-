"""
ui_edit_tab.py - 편집 탭 UI
기존 GIF/WebP/APNG 파일 열기 → 편집 → 저장
"""

import os
import threading
from pathlib import Path
from typing import Optional, List

import customtkinter as ctk
from PIL import Image, ImageTk

from config import settings
from utils import format_filesize, generate_output_name
from editor import load_frames, save_frames, apply_edits
from optimizer import auto_optimize


class EditTab(ctk.CTkFrame):
    """편집 탭"""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._file_path: Optional[str] = None
        self._frames: List[Image.Image] = []
        self._durations: List[int] = []
        self._loop: int = 0
        self._preview_index: int = 0
        self._preview_playing: bool = False
        self._preview_after_id = None
        self._working: bool = False
        self._open_folder_btn = None

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=2, minsize=450)
        self.grid_columnconfigure(1, weight=1, minsize=280)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # ════════════════════════════════════════
    # 좌측: 파일 열기 + 미리보기
    # ════════════════════════════════════════
    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color="gray14", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # 파일 열기
        file_frame = ctk.CTkFrame(left, fg_color="transparent")
        file_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        ctk.CTkButton(
            file_frame, text="📂 파일 열기", height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_file,
        ).pack(side="left", padx=(0, 8))

        self._file_label = ctk.CTkLabel(
            file_frame, text="GIF/WebP/APNG 파일을 선택하세요",
            font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._file_label.pack(side="left", fill="x", expand=True)

        # 미리보기
        self._preview_label = ctk.CTkLabel(
            left, text="미리보기",
            font=ctk.CTkFont(size=16), text_color="gray40",
        )
        self._preview_label.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)

        # 컨트롤
        ctrl = ctk.CTkFrame(left, fg_color="transparent", height=40)
        ctrl.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 4))

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

        self._info_label = ctk.CTkLabel(
            ctrl, text="", font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._info_label.pack(side="right", padx=8)

        # 진행률
        self._progress = ctk.CTkProgressBar(left, height=14)
        self._progress.grid(row=3, column=0, sticky="ew", padx=16, pady=4)
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=12), text_color="gray50",
        )
        self._status_label.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 12))

    # ════════════════════════════════════════
    # 우측: 편집 설정
    # ════════════════════════════════════════
    def _build_right_panel(self):
        right = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        pad = {"padx": 12, "pady": (4, 2), "sticky": "ew"}

        # ── 크롭 ──
        ctk.CTkLabel(right, text="✂️ 크롭",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, **pad)

        self._crop_var = ctk.StringVar(value="없음")
        self._crop_menu = ctk.CTkOptionMenu(
            right, values=["없음", "1:1", "16:9", "4:3", "3:2", "9:16"],
            variable=self._crop_var,
            font=ctk.CTkFont(size=12),
        )
        self._crop_menu.grid(row=1, column=0, **pad)

        # ── 리사이즈 ──
        ctk.CTkLabel(right, text="📐 리사이즈",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=2, column=0, **pad)

        self._resize_var = ctk.StringVar(value="원본")
        self._resize_menu = ctk.CTkOptionMenu(
            right, values=["원본", "75%", "50%", "25%"],
            variable=self._resize_var,
            font=ctk.CTkFont(size=12),
        )
        self._resize_menu.grid(row=3, column=0, **pad)

        # ── 회전 / 반전 ──
        ctk.CTkLabel(right, text="🔄 회전 / 반전",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=4, column=0, **pad)

        rot_frame = ctk.CTkFrame(right, fg_color="transparent")
        rot_frame.grid(row=5, column=0, **pad)

        self._rotate_var = ctk.StringVar(value="없음")
        ctk.CTkOptionMenu(
            rot_frame, values=["없음", "90°", "180°", "270°"],
            variable=self._rotate_var, font=ctk.CTkFont(size=12), width=90,
        ).pack(side="left", padx=(0, 8))

        self._flip_h_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(rot_frame, text="좌우", variable=self._flip_h_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=4)

        self._flip_v_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(rot_frame, text="상하", variable=self._flip_v_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=4)

        # ── 속도 ──
        ctk.CTkLabel(right, text="⏩ 속도",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=6, column=0, **pad)

        self._speed_var = ctk.StringVar(value="1.0x")
        self._speed_menu = ctk.CTkOptionMenu(
            right, values=["0.5x", "0.75x", "1.0x", "1.5x", "2.0x", "3.0x"],
            variable=self._speed_var, font=ctk.CTkFont(size=12),
        )
        self._speed_menu.grid(row=7, column=0, **pad)

        # ── 재생 효과 ──
        ctk.CTkLabel(right, text="🎬 재생 효과",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=8, column=0, **pad)

        effect_frame = ctk.CTkFrame(right, fg_color="transparent")
        effect_frame.grid(row=9, column=0, **pad)

        self._reverse_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(effect_frame, text="역재생", variable=self._reverse_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=4)

        self._boom_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(effect_frame, text="부메랑", variable=self._boom_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=4)

        # ── 색상 필터 ──
        ctk.CTkLabel(right, text="🎨 색상 필터",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=10, column=0, **pad)

        self._filter_var = ctk.StringVar(value="없음")
        self._filter_menu = ctk.CTkOptionMenu(
            right, values=["없음", "흑백", "세피아"],
            variable=self._filter_var, font=ctk.CTkFont(size=12),
        )
        self._filter_menu.grid(row=11, column=0, **pad)

        # 밝기
        bright_frame = ctk.CTkFrame(right, fg_color="transparent")
        bright_frame.grid(row=12, column=0, **pad)
        ctk.CTkLabel(bright_frame, text="밝기", font=ctk.CTkFont(size=12)).pack(side="left")
        self._bright_var = ctk.DoubleVar(value=1.0)
        self._bright_slider = ctk.CTkSlider(
            bright_frame, from_=0.3, to=2.0, variable=self._bright_var, width=140,
        )
        self._bright_slider.pack(side="left", padx=8)

        # 대비
        cont_frame = ctk.CTkFrame(right, fg_color="transparent")
        cont_frame.grid(row=13, column=0, **pad)
        ctk.CTkLabel(cont_frame, text="대비", font=ctk.CTkFont(size=12)).pack(side="left")
        self._contrast_var = ctk.DoubleVar(value=1.0)
        self._contrast_slider = ctk.CTkSlider(
            cont_frame, from_=0.3, to=2.0, variable=self._contrast_var, width=140,
        )
        self._contrast_slider.pack(side="left", padx=8)

        # ── 텍스트 ──
        ctk.CTkLabel(right, text="✍️ 텍스트",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=14, column=0, **pad)

        self._text_entry = ctk.CTkEntry(right, height=28, font=ctk.CTkFont(size=12),
                                         placeholder_text="텍스트 입력 (비우면 미적용)")
        self._text_entry.grid(row=15, column=0, **pad)

        text_opt = ctk.CTkFrame(right, fg_color="transparent")
        text_opt.grid(row=16, column=0, **pad)

        self._text_pos_var = ctk.StringVar(value="bottom")
        ctk.CTkOptionMenu(
            text_opt, values=["top", "center", "bottom", "top-left", "bottom-right"],
            variable=self._text_pos_var, font=ctk.CTkFont(size=11), width=100,
        ).pack(side="left", padx=(0, 8))

        self._frame_num_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(text_opt, text="프레임 번호", variable=self._frame_num_var,
                        font=ctk.CTkFont(size=12)).pack(side="left")

        # ── 출력 포맷 ──
        ctk.CTkLabel(right, text="📦 출력 포맷",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=17, column=0, **pad)

        self._format_var = ctk.StringVar(value="gif")
        fmt_frame = ctk.CTkFrame(right, fg_color="transparent")
        fmt_frame.grid(row=18, column=0, **pad)
        for i, (text, val) in enumerate([("GIF", "gif"), ("WebP", "webp"), ("APNG", "apng")]):
            ctk.CTkRadioButton(
                fmt_frame, text=text, variable=self._format_var, value=val,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=i, padx=8)

        # ── 출력 폴더 ──
        ctk.CTkLabel(right, text="📂 출력 폴더",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=19, column=0, **pad)

        out_frame = ctk.CTkFrame(right, fg_color="transparent")
        out_frame.grid(row=20, column=0, **pad)

        self._output_dir = ctk.StringVar(value=settings.get("output_dir"))
        ctk.CTkEntry(out_frame, textvariable=self._output_dir,
                     font=ctk.CTkFont(size=11), height=28
                     ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(out_frame, text="📁", width=30, height=28,
                      command=self._browse_output).pack(side="right")

        # ── 적용 버튼 ──
        self._apply_btn = ctk.CTkButton(
            right, text="🚀 편집 적용 + 저장", height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._apply,
        )
        self._apply_btn.grid(row=21, column=0, padx=12, pady=12, sticky="ew")

    # ════════════════════════════════════════
    # 파일 열기
    # ════════════════════════════════════════
    def _open_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="애니메이션 이미지 열기",
            filetypes=[
                ("애니메이션 이미지", "*.gif *.webp *.apng *.png"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        self._file_path = path
        name = Path(path).name
        if len(name) > 35:
            name = name[:32] + "..."
        self._file_label.configure(text=name, text_color="white")
        self._status_label.configure(text="로딩 중...", text_color="gray50")

        # 기존 프레임 정리
        for f in self._frames:
            try:
                f.close()
            except Exception:
                pass

        try:
            self._frames, self._durations, self._loop = load_frames(path)
            size = format_filesize(Path(path).stat().st_size)
            w, h = self._frames[0].width, self._frames[0].height
            self._info_label.configure(text=f"{w}x{h} | {len(self._frames)}프레임 | {size}")
            self._frame_label.configure(text=f"1/{len(self._frames)}")
            self._status_label.configure(text="✅ 로드 완료", text_color="#22c55e")

            # 입력 포맷 자동 설정
            ext = Path(path).suffix.lower()
            if ext == ".webp":
                self._format_var.set("webp")
            elif ext in (".apng", ".png"):
                self._format_var.set("apng")
            else:
                self._format_var.set("gif")

            self._show_frame(0)
        except Exception as e:
            self._status_label.configure(text=f"❌ 로드 실패: {e}", text_color="#ef4444")

    def add_file_from_drop(self, path: str):
        ext = Path(path).suffix.lower()
        if ext in ('.gif', '.webp', '.apng', '.png'):
            self._load_file(path)

    # ════════════════════════════════════════
    # 미리보기
    # ════════════════════════════════════════
    def _show_frame(self, index: int):
        if not self._frames or index >= len(self._frames):
            return
        try:
            img = self._frames[index].copy()
            img.thumbnail((500, 400), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._preview_label.configure(image=photo, text="")
            self._preview_label._photo = photo
            img.close()
            self._frame_label.configure(text=f"{index+1}/{len(self._frames)}")
        except Exception:
            pass

    def _toggle_preview(self):
        if self._preview_playing:
            self._stop_preview()
        else:
            self._start_preview()

    def _start_preview(self):
        if not self._frames:
            return
        self._preview_playing = True
        self._preview_index = 0
        self._play_btn.configure(text="⏸ 정지")
        self._play_next()

    def _stop_preview(self):
        self._preview_playing = False
        self._play_btn.configure(text="▶ 재생")
        if self._preview_after_id:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def _play_next(self):
        if not self._preview_playing or not self._frames:
            return
        self._show_frame(self._preview_index)
        delay = self._durations[self._preview_index] if self._preview_index < len(self._durations) else 100
        self._preview_index = (self._preview_index + 1) % len(self._frames)
        self._preview_after_id = self.after(delay, self._play_next)

    # ════════════════════════════════════════
    # 편집 적용
    # ════════════════════════════════════════
    def _build_edits(self) -> dict:
        edits = {}

        # 크롭
        crop = self._crop_var.get()
        if crop != "없음":
            edits["crop_ratio"] = crop

        # 리사이즈
        resize = self._resize_var.get()
        if resize != "원본":
            try:
                edits["resize_percent"] = int(resize.replace("%", ""))
            except ValueError:
                pass

        # 회전
        rot = self._rotate_var.get()
        if rot != "없음":
            edits["rotate"] = int(rot.replace("°", ""))

        # 반전
        if self._flip_h_var.get():
            edits["flip_h"] = True
        if self._flip_v_var.get():
            edits["flip_v"] = True

        # 속도
        try:
            speed = float(self._speed_var.get().replace("x", ""))
            if speed != 1.0:
                edits["speed"] = speed
        except ValueError:
            pass

        # 역재생 / 부메랑
        if self._reverse_var.get():
            edits["reverse"] = True
        if self._boom_var.get():
            edits["boomerang"] = True

        # 필터
        filt = self._filter_var.get()
        if filt == "흑백":
            edits["grayscale"] = True
        elif filt == "세피아":
            edits["sepia"] = True

        # 밝기 / 대비
        bright = round(self._bright_var.get(), 2)
        if bright != 1.0:
            edits["brightness"] = bright
        contrast = round(self._contrast_var.get(), 2)
        if contrast != 1.0:
            edits["contrast"] = contrast

        # 텍스트
        text = self._text_entry.get().strip()
        if text:
            edits["text"] = text
            edits["text_position"] = self._text_pos_var.get()

        # 프레임 번호
        if self._frame_num_var.get():
            edits["frame_numbers"] = True

        return edits

    def _apply(self):
        if self._working or not self._frames:
            if not self._frames:
                self._status_label.configure(text="⚠ 파일을 먼저 열어주세요", text_color="#f59e0b")
            return

        edits = self._build_edits()

        # 편집 없어도 포맷 변환은 허용
        action = "포맷 변환 중..." if not edits else "편집 적용 중..."

        self._working = True
        self._apply_btn.configure(state="disabled")
        self._progress.set(0)
        self._status_label.configure(text=action, text_color="white")

        threading.Thread(target=self._run_edit, args=(edits,), daemon=True).start()

    def _run_edit(self, edits: dict):
        try:
            # 원본 복사 후 편집
            frames_copy = [f.copy() for f in self._frames]
            durations_copy = list(self._durations)

            self.after(0, lambda: self._progress.set(0.3))
            edited_frames, edited_durations = apply_edits(frames_copy, durations_copy, edits)

            self.after(0, lambda: self._progress.set(0.6))
            self.after(0, lambda: self._status_label.configure(text="저장 중..."))

            # 저장
            fmt = self._format_var.get()
            ext = "apng" if fmt == "apng" else fmt
            base = Path(self._file_path).stem if self._file_path else "edited"
            output_path = generate_output_name(f"{base}_edited", ext, self._output_dir.get())

            save_frames(edited_frames, edited_durations, output_path, fmt, self._loop)

            # 메모리 정리
            for f in edited_frames:
                try:
                    f.close()
                except Exception:
                    pass

            self.after(0, lambda: self._on_edit_done(output_path))

        except Exception as e:
            self.after(0, lambda: self._on_edit_done(None, str(e)))

    def _on_edit_done(self, result: Optional[str], error: str = ""):
        self._working = False
        self._apply_btn.configure(state="normal")

        if result and Path(result).exists():
            size = format_filesize(Path(result).stat().st_size)
            self._status_label.configure(
                text=f"✅ 저장 완료! {Path(result).name} ({size})",
                text_color="#22c55e",
            )
            self._progress.set(1.0)
            self._show_open_folder(str(Path(result).parent))
        else:
            self._progress.set(0)
            self._status_label.configure(
                text=f"❌ 편집 실패: {error}" if error else "❌ 편집 실패",
                text_color="#ef4444",
            )

    # ════════════════════════════════════════
    # 유틸
    # ════════════════════════════════════════
    def _browse_output(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(initialdir=self._output_dir.get())
        if d:
            self._output_dir.set(d)
            settings.set("output_dir", d)
            settings.save()

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
            self._status_label.master,
            text="📂 출력 폴더 열기", height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#16a34a", hover_color="#15803d",
            command=open_it,
        )
        self._open_folder_btn.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 8))
