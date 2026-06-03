"""
ui_record_tab.py - 화면 녹화 탭 UI
녹화 제어, 설정, 타이머, 변환
"""

import os
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from config import settings
from utils import format_filesize, generate_output_name, ffmpeg_available
from recorder import (
    ScreenRecorder, RecordSettings, RecordRegion, RecordState,
)
from optimizer import auto_optimize


class RecordTab(ctk.CTkFrame):
    """화면 녹화 탭"""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._recorder = ScreenRecorder()
        self._timer_after_id = None
        self._last_result: Optional[str] = None
        self._open_folder_btn = None

        self._recorder.set_callbacks(
            on_frame=self._on_frame_callback,
            on_state=self._on_state_callback,
            on_convert_progress=self._on_convert_callback,
            on_auto_stop=self._on_auto_stop_callback,
        )

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=2, minsize=450)
        self.grid_columnconfigure(1, weight=1, minsize=280)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # ════════════════════════════════════════
    # 좌측: 녹화 컨트롤 + 타이머
    # ════════════════════════════════════════
    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color="gray14", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        left.grid_columnconfigure(0, weight=1)

        # ── mss 상태 체크 ──
        mss_ok = ScreenRecorder.mss_available()

        # ── 타이머 표시 ──
        self._timer_label = ctk.CTkLabel(
            left, text="00:00.0",
            font=ctk.CTkFont(size=48, weight="bold"),
            text_color="#22c55e" if mss_ok else "gray40",
        )
        self._timer_label.grid(row=0, column=0, pady=(40, 8))

        self._frame_count_label = ctk.CTkLabel(
            left, text="0 프레임",
            font=ctk.CTkFont(size=14), text_color="gray50",
        )
        self._frame_count_label.grid(row=1, column=0, pady=(0, 20))

        # ── 녹화 버튼 그룹 ──
        btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=8)

        self._rec_btn = ctk.CTkButton(
            btn_frame, text="⏺ 녹화 시작", width=140, height=48,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#dc2626", hover_color="#b91c1c",
            command=self._on_record_btn,
        )
        self._rec_btn.pack(side="left", padx=8)

        self._pause_btn = ctk.CTkButton(
            btn_frame, text="⏸ 일시정지", width=120, height=48,
            font=ctk.CTkFont(size=14),
            fg_color="gray30", hover_color="gray40",
            command=self._on_pause_btn,
        )
        self._pause_btn.pack(side="left", padx=8)
        self._pause_btn.configure(state="disabled")

        # ── 영역 선택 ──
        region_frame = ctk.CTkFrame(left, fg_color="transparent")
        region_frame.grid(row=3, column=0, pady=(20, 4))

        ctk.CTkLabel(region_frame, text="📐 녹화 영역",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 12))

        self._region_var = ctk.StringVar(value="전체 화면")
        self._region_menu = ctk.CTkOptionMenu(
            region_frame,
            values=["전체 화면", "영역 지정"],
            variable=self._region_var,
            font=ctk.CTkFont(size=12),
            command=self._on_region_change,
        )
        self._region_menu.pack(side="left")

        # 커스텀 영역 입력 (기본 숨김)
        self._custom_region_frame = ctk.CTkFrame(left, fg_color="gray20", corner_radius=8)
        self._custom_region_frame.grid(row=4, column=0, padx=40, pady=4, sticky="ew")
        self._custom_region_frame.grid_remove()

        entries_frame = ctk.CTkFrame(self._custom_region_frame, fg_color="transparent")
        entries_frame.pack(padx=12, pady=8)

        for i, (label, default) in enumerate([("X:", "0"), ("Y:", "0"), ("W:", "800"), ("H:", "600")]):
            ctk.CTkLabel(entries_frame, text=label, font=ctk.CTkFont(size=12)).grid(row=0, column=i*2, padx=2)
            entry = ctk.CTkEntry(entries_frame, width=60, height=28, font=ctk.CTkFont(size=12))
            entry.insert(0, default)
            entry.grid(row=0, column=i*2+1, padx=2)
            setattr(self, f"_region_{label[0].lower()}_entry", entry)

        # ── 단축키 안내 ──
        self._hotkey_label = ctk.CTkLabel(
            left, text="💡 녹화 중 이 창을 최소화해도 녹화는 계속됩니다",
            font=ctk.CTkFont(size=11), text_color="gray50",
        )
        self._hotkey_label.grid(row=5, column=0, pady=(12, 4))

        # ── 진행률 ──
        self._progress = ctk.CTkProgressBar(left, height=14)
        self._progress.grid(row=6, column=0, sticky="ew", padx=40, pady=(16, 4))
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(
            left, text="mss 라이브러리 필요: pip install mss" if not mss_ok else "녹화 준비 완료",
            font=ctk.CTkFont(size=12),
            text_color="#ef4444" if not mss_ok else "gray50",
        )
        self._status_label.grid(row=7, column=0, padx=40, pady=(0, 12))

        if not mss_ok:
            self._rec_btn.configure(state="disabled")

    # ════════════════════════════════════════
    # 우측: 설정
    # ════════════════════════════════════════
    def _build_right_panel(self):
        right = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        pad = {"padx": 12, "pady": (4, 2), "sticky": "ew"}

        # ── 출력 포맷 ──
        ctk.CTkLabel(right, text="📦 출력 포맷",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, **pad)

        self._format_var = ctk.StringVar(value=settings.get("record_output_format"))
        fmt_frame = ctk.CTkFrame(right, fg_color="transparent")
        fmt_frame.grid(row=1, column=0, **pad)
        for i, (text, val) in enumerate([("GIF", "gif"), ("WebP", "webp"), ("APNG", "apng")]):
            ctk.CTkRadioButton(
                fmt_frame, text=text, variable=self._format_var, value=val,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=i, padx=8)

        # ── FPS ──
        ctk.CTkLabel(right, text="🎞️ FPS",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=2, column=0, **pad)

        self._fps_var = ctk.StringVar(value="15")
        self._fps_menu = ctk.CTkOptionMenu(
            right, values=["10", "15", "20", "24", "30"],
            variable=self._fps_var,
            font=ctk.CTkFont(size=12),
        )
        self._fps_menu.grid(row=3, column=0, **pad)

        # ── 해상도 ──
        ctk.CTkLabel(right, text="📐 해상도",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=4, column=0, **pad)

        self._scale_var = ctk.StringVar(value="100%")
        self._scale_menu = ctk.CTkOptionMenu(
            right, values=["100%", "75%", "50%"],
            variable=self._scale_var,
            font=ctk.CTkFont(size=12),
        )
        self._scale_menu.grid(row=5, column=0, **pad)

        # ── 최대 녹화 시간 ──
        ctk.CTkLabel(right, text="⏱️ 최대 녹화 시간",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=6, column=0, **pad)

        self._maxdur_var = ctk.StringVar(value="60초")
        self._maxdur_menu = ctk.CTkOptionMenu(
            right, values=["10초", "30초", "60초", "120초"],
            variable=self._maxdur_var,
            font=ctk.CTkFont(size=12),
        )
        self._maxdur_menu.grid(row=7, column=0, **pad)

        # ── 품질 ──
        ctk.CTkLabel(right, text="💎 품질 (WebP)",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=8, column=0, **pad)

        self._quality_var = ctk.IntVar(value=80)
        q_frame = ctk.CTkFrame(right, fg_color="transparent")
        q_frame.grid(row=9, column=0, **pad)

        self._quality_slider = ctk.CTkSlider(
            q_frame, from_=10, to=100,
            variable=self._quality_var,
            command=self._on_quality_change,
            width=160,
        )
        self._quality_slider.pack(side="left", padx=(0, 8))
        self._quality_label = ctk.CTkLabel(
            q_frame, text="80%", font=ctk.CTkFont(size=12),
        )
        self._quality_label.pack(side="left")

        # ── 반복 ──
        ctk.CTkLabel(right, text="🔁 반복",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=10, column=0, **pad)

        self._loop_var = ctk.StringVar(value="무한 반복")
        self._loop_menu = ctk.CTkOptionMenu(
            right, values=["무한 반복", "1회", "2회", "3회"],
            variable=self._loop_var,
            font=ctk.CTkFont(size=12),
        )
        self._loop_menu.grid(row=11, column=0, **pad)

        # ── 목표 용량 ──
        ctk.CTkLabel(right, text="🎯 목표 용량",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=12, column=0, **pad)

        opt_frame = ctk.CTkFrame(right, fg_color="transparent")
        opt_frame.grid(row=13, column=0, **pad)

        self._optimize_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opt_frame, text="자동 최적화",
            variable=self._optimize_var,
            font=ctk.CTkFont(size=12),
            command=self._on_optimize_toggle,
        ).pack(side="left")

        self._target_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._target_frame.grid(row=14, column=0, **pad)
        self._target_frame.grid_remove()

        ctk.CTkLabel(self._target_frame, text="목표:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._target_kb_entry = ctk.CTkEntry(self._target_frame, width=70, height=28,
                                              font=ctk.CTkFont(size=12))
        self._target_kb_entry.insert(0, "5000")
        self._target_kb_entry.pack(side="left", padx=4)
        ctk.CTkLabel(self._target_frame, text="KB",
                     font=ctk.CTkFont(size=11), text_color="gray50").pack(side="left")

        # ── 출력 폴더 ──
        ctk.CTkLabel(right, text="📂 출력 폴더",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=15, column=0, **pad)

        out_frame = ctk.CTkFrame(right, fg_color="transparent")
        out_frame.grid(row=16, column=0, **pad)

        self._output_dir = ctk.StringVar(value=settings.get("output_dir"))
        self._out_entry = ctk.CTkEntry(out_frame, textvariable=self._output_dir,
                                        font=ctk.CTkFont(size=11), height=28)
        self._out_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(out_frame, text="📁", width=30, height=28,
                      command=self._browse_output).pack(side="right")

    # ════════════════════════════════════════
    # 설정 콜백
    # ════════════════════════════════════════
    def _on_region_change(self, val=None):
        if "영역" in self._region_var.get():
            self._custom_region_frame.grid()
        else:
            self._custom_region_frame.grid_remove()

    def _on_quality_change(self, val=None):
        self._quality_label.configure(text=f"{self._quality_var.get()}%")

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

    # ════════════════════════════════════════
    # 설정 → RecordSettings 빌드
    # ════════════════════════════════════════
    def _build_settings(self) -> RecordSettings:
        s = RecordSettings()
        s.output_format = self._format_var.get()
        try:
            s.fps = int(self._fps_var.get())
        except ValueError:
            s.fps = 15
        s.quality = self._quality_var.get()
        s.output_dir = self._output_dir.get()

        # 해상도
        scale_str = self._scale_var.get().replace("%", "")
        try:
            s.scale = int(scale_str)
        except ValueError:
            s.scale = 100

        # 최대 시간
        dur_str = self._maxdur_var.get().replace("초", "")
        try:
            s.max_duration = int(dur_str)
        except ValueError:
            s.max_duration = 60

        # 반복
        loop_str = self._loop_var.get()
        if "무한" in loop_str:
            s.loop = 0
        else:
            try:
                s.loop = int(loop_str.replace("회", ""))
            except ValueError:
                s.loop = 0

        # 영역
        if "영역" in self._region_var.get():
            try:
                s.region = RecordRegion(
                    x=int(self._region_x_entry.get()),
                    y=int(self._region_y_entry.get()),
                    w=int(self._region_w_entry.get()),
                    h=int(self._region_h_entry.get()),
                )
            except ValueError:
                s.region = RecordRegion()  # 전체 화면 폴백
        else:
            s.region = RecordRegion()

        return s

    # ════════════════════════════════════════
    # 녹화 제어
    # ════════════════════════════════════════
    def _on_record_btn(self):
        state = self._recorder.state
        if state == RecordState.IDLE:
            self._start_recording()
        elif state in (RecordState.RECORDING, RecordState.PAUSED):
            self._stop_recording()

    def _on_pause_btn(self):
        self._recorder.pause()
        if self._recorder.state == RecordState.PAUSED:
            self._pause_btn.configure(text="▶ 재개")
            self._timer_label.configure(text_color="#f59e0b")
        else:
            self._pause_btn.configure(text="⏸ 일시정지")
            self._timer_label.configure(text_color="#dc2626")

    def _start_recording(self):
        s = self._build_settings()

        # 이전 폴더 열기 버튼 제거
        if hasattr(self, '_open_folder_btn') and self._open_folder_btn:
            try:
                self._open_folder_btn.destroy()
            except Exception:
                pass
            self._open_folder_btn = None

        self._rec_btn.configure(text="⏹ 녹화 중지", fg_color="#991b1b")
        self._pause_btn.configure(state="normal", text="⏸ 일시정지")
        self._region_menu.configure(state="disabled")
        self._timer_label.configure(text="00:00.0", text_color="#dc2626")
        self._frame_count_label.configure(text="0 프레임")
        self._progress.set(0)
        self._status_label.configure(text="🔴 녹화 중...", text_color="#dc2626")

        settings.set("record_output_format", s.output_format)
        settings.save()

        self._recorder.start(s)
        self._start_timer()

    def _stop_recording(self):
        self._stop_timer()
        self._rec_btn.configure(text="⏺ 녹화 시작", fg_color="#dc2626", state="disabled")
        self._pause_btn.configure(state="disabled")
        self._status_label.configure(text="변환 중...", text_color="white")
        self._timer_label.configure(text_color="#22c55e")

        self._recorder.stop()

        # 변환은 별도 스레드
        threading.Thread(target=self._run_convert, daemon=True).start()

    def _run_convert(self):
        result = self._recorder.convert()

        # 최적화
        if result and self._optimize_var.get():
            try:
                target_kb = int(self._target_kb_entry.get())
            except ValueError:
                target_kb = 5000

            def opt_cb(msg):
                self.after(0, lambda m=msg: self._status_label.configure(text=f"🎯 {m}"))

            optimized = auto_optimize(result, target_kb, on_progress=opt_cb)
            if optimized and optimized != result:
                import shutil
                try:
                    shutil.copy2(optimized, result)
                    Path(optimized).unlink(missing_ok=True)
                except PermissionError:
                    result = optimized
                except Exception:
                    result = optimized

        self._last_result = result
        self.after(0, lambda: self._on_convert_done(result))

    def _on_convert_done(self, result: Optional[str]):
        self._rec_btn.configure(state="normal")
        self._region_menu.configure(state="normal")

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
            self._status_label.configure(text="❌ 변환 실패", text_color="#ef4444")

    # ════════════════════════════════════════
    # 타이머
    # ════════════════════════════════════════
    def _start_timer(self):
        self._update_timer()

    def _stop_timer(self):
        if self._timer_after_id:
            self.after_cancel(self._timer_after_id)
            self._timer_after_id = None

    def _update_timer(self):
        if self._recorder.state not in (RecordState.RECORDING, RecordState.PAUSED):
            return

        elapsed = self._recorder.elapsed
        m, s = divmod(int(elapsed), 60)
        tenths = int((elapsed - int(elapsed)) * 10)
        self._timer_label.configure(text=f"{m:02d}:{s:02d}.{tenths}")

        # 최대 시간 대비 진행률
        max_dur = self._recorder.settings.max_duration
        if max_dur > 0:
            self._progress.set(min(1.0, elapsed / max_dur))

        self._timer_after_id = self.after(100, self._update_timer)

    # ════════════════════════════════════════
    # 콜백 (메인 스레드로 전달)
    # ════════════════════════════════════════
    def _on_frame_callback(self, frame_count: int, elapsed: float):
        self.after(0, lambda: self._frame_count_label.configure(text=f"{frame_count} 프레임"))

    def _on_state_callback(self, state: str):
        pass  # 상태 변경 알림 (현재 미사용)

    def _on_auto_stop_callback(self):
        """max_duration 도달로 캡처 루프가 자동 종료됨 → UI에서 중지+변환 트리거"""
        self.after(0, self._stop_recording)

    def _on_convert_callback(self, pct: int, msg: str):
        self.after(0, lambda p=pct, m=msg: self._update_convert_progress(p, m))

    def _update_convert_progress(self, pct: int, msg: str):
        self._progress.set(pct / 100)
        self._status_label.configure(text=msg)

    # ════════════════════════════════════════
    # 폴더 열기
    # ════════════════════════════════════════
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
        self._open_folder_btn.grid(row=8, column=0, padx=40, pady=(4, 8), sticky="ew")
