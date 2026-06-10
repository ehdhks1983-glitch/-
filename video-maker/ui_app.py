"""
ui_app.py - 영상 제작기 메인 UI
탭 2개: 📝 영상 기획 → 📱 쇼츠 제작 (기획 결과를 쇼츠로 바로 전달)
"""

import sys
from pathlib import Path

import customtkinter as ctk

from config import APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW_SIZE
from ui_planner_tab import PlannerTab
from ui_shorts_tab import ShortsTab


class VideoMakerApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)

        try:
            ico = Path(__file__).parent / "app_icon.ico"
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabs()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_header(self):
        header = ctk.CTkFrame(self, height=48, fg_color="gray10", corner_radius=0)
        header.grid(row=0, column=0, sticky="new")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text=f"🎬 {APP_NAME}",
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=10)

        ctk.CTkButton(header, text="💧 워터마크", width=90, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color="#0ea5e9", hover_color="#0284c7",
                      command=self._open_watermark
                      ).grid(row=0, column=2, sticky="e", padx=(0, 8), pady=10)

        ctk.CTkLabel(header, text=f"v{APP_VERSION}",
                     font=ctk.CTkFont(size=11), text_color="gray50"
                     ).grid(row=0, column=3, sticky="e", padx=(0, 16), pady=10)

    def _open_watermark(self):
        try:
            from watermark_dialog import WatermarkDialog
            WatermarkDialog(self).focus()
        except Exception:
            pass

    def _build_tabs(self):
        self._tabview = ctk.CTkTabview(
            self, fg_color="gray12",
            segmented_button_fg_color="gray20",
            segmented_button_selected_color="#2563eb",
            segmented_button_unselected_color="gray30",
        )
        self._tabview.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

        tabs = {"📝 영상 기획": PlannerTab, "📱 쇼츠 제작": ShortsTab}
        self._tab_instances = {}
        for name, cls in tabs.items():
            tab = self._tabview.add(name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            inst = cls(tab)
            inst.grid(row=0, column=0, sticky="nsew")
            self._tab_instances[name] = inst

        self._planner_tab = self._tab_instances["📝 영상 기획"]
        self._shorts_tab = self._tab_instances["📱 쇼츠 제작"]

        # 기획 → 쇼츠 연결
        try:
            self._planner_tab._to_shorts = self._plan_to_shorts
        except Exception:
            pass

        self._tabview.set("📝 영상 기획")

    def _plan_to_shorts(self, items):
        try:
            self._shorts_tab.load_from_plan(items)
            self._tabview.set("📱 쇼츠 제작")
        except Exception:
            pass
