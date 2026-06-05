"""
ui_app.py - 메인 앱 UI (6단계 다듬기 완료)
상태바, FFmpeg 감지, 드래그앤드롭, 탭 구조
"""

import sys
import json
import ssl
import subprocess
import threading
import urllib.request
import webbrowser
from pathlib import Path

import customtkinter as ctk

from config import APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW_SIZE, UPDATE_URL, settings
from utils import ffmpeg_available, find_ffmpeg
from ui_merge_tab import MergeTab
from ui_video_tab import VideoTab
from ui_record_tab import RecordTab
from ui_edit_tab import EditTab
from ui_shorts_tab import ShortsTab
from ui_planner_tab import PlannerTab


class GifMakerApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)

        # 앱 아이콘
        try:
            # --onefile: _MEIPASS 안에 있음
            if getattr(sys, '_MEIPASS', None):
                icon_path = Path(sys._MEIPASS) / "app_icon.ico"
            else:
                icon_path = Path(__file__).parent / "app_icon.ico"
            # 설치 폴더에서도 찾기
            if not icon_path.exists():
                icon_path = Path(sys.executable).parent / "app_icon.ico"
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except Exception:
            pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # 탭 영역

        self._build_header()
        self._build_tabs()
        self._build_statusbar()
        self._setup_dnd()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 자동 업데이트 체크 (2초 후)
        self.after(2000, self._check_for_update)

    # ════════════════════════════════════════
    # 헤더
    # ════════════════════════════════════════
    def _build_header(self):
        header = ctk.CTkFrame(self, height=48, fg_color="gray10", corner_radius=0)
        header.grid(row=0, column=0, sticky="new")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text=f"🎞️ {APP_NAME}",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=10)

        # 💧 워터마크 + ℹ️ 정보 버튼
        btns = ctk.CTkFrame(header, fg_color="transparent")
        btns.grid(row=0, column=2, sticky="e", padx=(0, 8), pady=10)
        ctk.CTkButton(
            btns, text="💧 워터마크", width=90, height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#0ea5e9", hover_color="#0284c7",
            command=self._open_watermark,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btns, text="ℹ️ 정보", width=70, height=28,
            font=ctk.CTkFont(size=11),
            fg_color="gray25", hover_color="gray30",
            command=self._open_about,
        ).pack(side="left")

        ctk.CTkLabel(
            header, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11), text_color="gray50",
        ).grid(row=0, column=3, sticky="e", padx=(0, 16), pady=10)

    def _open_about(self):
        """정보/도움말 다이얼로그 열기"""
        try:
            from about_dialog import AboutDialog
            dialog = AboutDialog(self)
            dialog.focus()
        except Exception:
            pass

    def _open_watermark(self):
        """워터마크 설정 창 열기"""
        try:
            from watermark_dialog import WatermarkDialog
            dialog = WatermarkDialog(self)
            dialog.focus()
        except Exception:
            pass

    # ════════════════════════════════════════
    # 탭
    # ════════════════════════════════════════
    def _build_tabs(self):
        self._tabview = ctk.CTkTabview(
            self, fg_color="gray12",
            segmented_button_fg_color="gray20",
            segmented_button_selected_color="#2563eb",
            segmented_button_unselected_color="gray30",
        )
        self._tabview.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))

        tabs = {
            "📝 영상 기획": PlannerTab,
            "📱 쇼츠 제작": ShortsTab,
            "🖼️ 이미지 합치기": MergeTab,
            "🎬 영상 → 움짤": VideoTab,
            "🔴 화면 녹화": RecordTab,
            "✏️ 편집": EditTab,
        }

        self._tab_instances = {}
        for name, cls in tabs.items():
            tab = self._tabview.add(name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            instance = cls(tab)
            instance.grid(row=0, column=0, sticky="nsew")
            self._tab_instances[name] = instance

        # 편의 참조
        self._planner_tab = self._tab_instances["📝 영상 기획"]
        self._merge_tab = self._tab_instances["🖼️ 이미지 합치기"]
        self._video_tab = self._tab_instances["🎬 영상 → 움짤"]
        self._shorts_tab = self._tab_instances["📱 쇼츠 제작"]
        self._record_tab = self._tab_instances["🔴 화면 녹화"]
        self._edit_tab = self._tab_instances["✏️ 편집"]

        # 기획 → 쇼츠 연결 (기획서 장면을 쇼츠 탭으로 보냄)
        try:
            self._planner_tab._to_shorts = self._plan_to_shorts
        except Exception:
            pass

        self._tabview.set("📝 영상 기획")

    def _plan_to_shorts(self, items):
        """영상 기획 → 쇼츠 제작: 장면 자동 채우고 탭 전환"""
        try:
            self._shorts_tab.load_from_plan(items)
            self._tabview.set("📱 쇼츠 제작")
        except Exception:
            pass

    # ════════════════════════════════════════
    # 하단 상태바
    # ════════════════════════════════════════
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=28, fg_color="gray10", corner_radius=0)
        bar.grid(row=2, column=0, sticky="sew")
        bar.grid_columnconfigure(1, weight=1)

        # FFmpeg 상태
        ff = find_ffmpeg()
        if ff:
            ff_text = f"✅ FFmpeg: {Path(ff).name}"
            ff_color = "gray50"
        else:
            ff_text = "⚠ FFmpeg 없음 — 영상 변환/녹화 제한"
            ff_color = "#f59e0b"

        ctk.CTkLabel(
            bar, text=ff_text,
            font=ctk.CTkFont(size=10), text_color=ff_color,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=2)

        # 출력 폴더
        out_dir = settings.get("output_dir")
        if len(out_dir) > 50:
            out_dir = "..." + out_dir[-47:]

        ctk.CTkLabel(
            bar, text=f"📂 {out_dir}",
            font=ctk.CTkFont(size=10), text_color="gray50",
        ).grid(row=0, column=1, sticky="e", padx=12, pady=2)

    # ════════════════════════════════════════
    # 드래그앤드롭
    # ════════════════════════════════════════
    def _setup_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except (ImportError, Exception):
            pass

    def _on_drop(self, event):
        raw = event.data
        if '{' in raw:
            import re
            paths = re.findall(r'\{([^}]+)\}', raw)
        else:
            paths = raw.split()

        current = self._tabview.get()
        if "이미지" in current:
            self._merge_tab.add_files_from_drop(paths)
        elif "쇼츠" in current:
            for p in paths:
                self._shorts_tab.add_file_from_drop(p)
        elif "영상" in current and paths:
            self._video_tab.add_file_from_drop(paths[0])
        elif "편집" in current and paths:
            self._edit_tab.add_file_from_drop(paths[0])

    # ════════════════════════════════════════
    # 🔄 자동 업데이트
    # ════════════════════════════════════════
    def _check_for_update(self):
        """GitHub에서 최신 버전 체크"""
        def check():
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                latest = data.get("version", "")
                download_url = data.get("download_url", "")
                message = data.get("message", "")
                if latest and latest != APP_VERSION and download_url:
                    def ver(v):
                        return tuple(int(x) for x in v.split("."))
                    if ver(latest) > ver(APP_VERSION):
                        self.after(0, lambda: self._show_update_popup(latest, download_url, message))
            except Exception:
                pass
        threading.Thread(target=check, daemon=True).start()

    def _show_update_popup(self, latest, download_url, message):
        """업데이트 팝업 → 자동 다운로드"""
        from tkinter import messagebox
        msg = f"새 버전이 있습니다!\n\n현재: v{APP_VERSION}\n최신: v{latest}\n"
        if message:
            msg += f"\n{message}\n"
        msg += "\n지금 업데이트 하시겠습니까?"
        ok = messagebox.askyesno("업데이트", msg)
        if ok and download_url:
            self._auto_update(download_url, latest)

    def _auto_update(self, download_url, latest):
        """자동 다운로드 + 설치"""
        import tempfile
        self.title(f"⬇️ 업데이트 다운로드 중...")

        def download():
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(download_url, headers={"User-Agent": APP_NAME})
                temp = Path(tempfile.gettempdir()) / "GIFMakerPro_Setup.exe"
                with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                    with open(temp, 'wb') as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                self.after(0, lambda: self._run_installer(temp))
            except Exception:
                self.after(0, lambda: self._update_failed(download_url))
        threading.Thread(target=download, daemon=True).start()

    def _update_failed(self, download_url):
        """다운로드 실패 시 브라우저로 안내"""
        from tkinter import messagebox
        self.title(f"{APP_NAME} v{APP_VERSION}")
        messagebox.showwarning("다운로드 실패",
            "자동 다운로드에 실패했습니다.\n브라우저에서 직접 다운로드합니다.")
        webbrowser.open(download_url)

    def _run_installer(self, path):
        """앱 종료 → 3초 후 설치"""
        import tempfile
        from tkinter import messagebox
        bat = Path(tempfile.gettempdir()) / "gifmaker_update.bat"
        bat.write_text(
            f'@echo off\nping 127.0.0.1 -n 4 > nul\nstart "" "{path}"\ndel "%~f0"\n',
            encoding='cp949'
        )
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x08000000)
        messagebox.showinfo("업데이트", "설치가 곧 시작됩니다.\n앱이 종료됩니다.")
        self.destroy()
        sys.exit(0)

    # ════════════════════════════════════════
    # 종료
    # ════════════════════════════════════════
    def _on_closing(self):
        try:
            self._record_tab._recorder.cancel()
        except Exception:
            pass
        try:
            self._video_tab._cleanup_cache()
        except Exception:
            pass
        self.destroy()
