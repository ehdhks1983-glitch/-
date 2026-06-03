"""Main application window: nav + content + Start/Pause/Stop + live log.

The window is a thin coordinator. Long work runs on
:class:`~core.automation_controller.AutomationController`; state changes are
marshalled back onto the Tk main thread with ``after`` so widgets are only ever
touched from one thread and the UI never freezes.
"""

from __future__ import annotations

import customtkinter as ctk

import config
from core.automation_controller import AutomationController, JobControl, WorkerState
from core.logging_setup import add_ui_handler, get_logger, setup_logging
from core.settings_store import SettingsStore
from core.ui_bridge import LogQueue
from ui.tab_account import AccountTab
from ui.tab_brand import BrandTab
from ui.widgets import LogPanel

_STATE_LABELS = {
    WorkerState.IDLE: ("대기 / Idle", "#6b7280"),
    WorkerState.RUNNING: ("실행 중 / Running", "#16a34a"),
    WorkerState.PAUSED: ("일시정지 / Paused", "#d97706"),
    WorkerState.STOPPING: ("중지 중 / Stopping", "#dc2626"),
}


class AppWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        setup_logging()
        ctk.set_appearance_mode(config.UI_THEME)
        ctk.set_default_color_theme(config.UI_COLOR_THEME)

        self.title(config.APP_TITLE)
        self.minsize(*config.WINDOW_MIN_SIZE)
        self.geometry("1100x720")

        self.store = SettingsStore().load()
        self.log_queue = LogQueue()
        self.controller = AutomationController(on_state_change=self._on_state_change)
        add_ui_handler(self.log_queue.push)
        self.log = get_logger("ui")

        self._tabs: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        # The job Start runs. Replaced by the real pipeline in later stages.
        self._job = self._demo_job

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log.info("UI 준비 완료 / ready")
        self._apply_state(WorkerState.IDLE)

    # ------------------------------------------------------------------ layout
    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(2, weight=2)

        # --- left nav ---
        nav = ctk.CTkFrame(self, width=210, corner_radius=0)
        nav.grid(row=0, column=0, rowspan=2, sticky="nsew")
        nav.grid_propagate(False)
        ctk.CTkLabel(nav, text=config.APP_TITLE, font=ctk.CTkFont(size=17, weight="bold")).pack(
            padx=16, pady=(18, 4), anchor="w")
        ctk.CTkLabel(nav, text="공식 API · 반자동", text_color="#8b95a7").pack(
            padx=16, pady=(0, 16), anchor="w")
        self._nav_holder = nav

        # --- content host ---
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=0, column=1, sticky="nsew", padx=10, pady=(10, 0))
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._register_tabs()

        # --- control bar ---
        bar = ctk.CTkFrame(self)
        bar.grid(row=1, column=1, sticky="ew", padx=10, pady=10)
        self.btn_start = ctk.CTkButton(bar, text="▶ 시작", width=110, command=self._on_start)
        self.btn_pause = ctk.CTkButton(bar, text="⏸ 일시정지", width=110, command=self._on_pause)
        self.btn_stop = ctk.CTkButton(bar, text="■ 중지", width=110, fg_color="#b91c1c",
                                      hover_color="#7f1d1d", command=self._on_stop)
        self.btn_start.pack(side="left", padx=6, pady=8)
        self.btn_pause.pack(side="left", padx=6, pady=8)
        self.btn_stop.pack(side="left", padx=6, pady=8)
        self.status_label = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.status_label.pack(side="right", padx=14)

        # --- log panel ---
        self.log_panel = LogPanel(self, self.log_queue)
        self.log_panel.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.log_panel.start()

    def _register_tabs(self) -> None:
        self.add_tab("account", AccountTab(self._content, self.store))
        self.add_tab("brand", BrandTab(self._content, self.store))
        # Later stages register: "create" (tab_create), "schedule" (tab_schedule).
        self._show("account")

    def add_tab(self, name: str, frame: ctk.CTkFrame, label: str | None = None) -> None:
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_remove()
        self._tabs[name] = frame
        btn = ctk.CTkButton(self._nav_holder, text=label or _default_nav_label(name),
                            anchor="w", command=lambda n=name: self._show(n))
        btn.pack(fill="x", padx=12, pady=4)
        self._nav_buttons[name] = btn

    def _show(self, name: str) -> None:
        for n, frame in self._tabs.items():
            frame.grid_remove()
        self._tabs[name].grid()
        for n, btn in self._nav_buttons.items():
            btn.configure(fg_color=("#3b82f6" if n == name else "transparent"))

    # ------------------------------------------------------------- controls
    def _on_start(self) -> None:
        if self.controller.is_active:
            return
        self.log.info("작업 시작 / start requested")
        self.controller.start(self._job, on_error=self._on_job_error)

    def _on_pause(self) -> None:
        if self.controller.state == WorkerState.RUNNING:
            self.controller.pause()
        elif self.controller.state == WorkerState.PAUSED:
            self.controller.resume()

    def _on_stop(self) -> None:
        self.controller.stop()

    def _on_job_error(self, exc: BaseException) -> None:
        self.after(0, lambda: get_logger("ui").error("작업 실패 / job failed: %s", exc))

    # ---------------------------------------------------------- state sync
    def _on_state_change(self, state: WorkerState) -> None:
        # Called from the worker thread - bounce to the main thread.
        self.after(0, self._apply_state, state)

    def _apply_state(self, state: WorkerState) -> None:
        text, color = _STATE_LABELS.get(state, ("?", "#6b7280"))
        self.status_label.configure(text=text, text_color=color)
        idle = state == WorkerState.IDLE
        running = state == WorkerState.RUNNING
        paused = state == WorkerState.PAUSED
        self.btn_start.configure(state="normal" if idle else "disabled")
        self.btn_stop.configure(state="disabled" if idle else "normal")
        self.btn_pause.configure(
            state="normal" if (running or paused) else "disabled",
            text="▶ 재개" if paused else "⏸ 일시정지",
        )

    # ----------------------------------------------------------- demo job
    def _demo_job(self, control: JobControl) -> None:
        """Stage-2 placeholder proving async start/pause/stop + live logging."""
        log = get_logger("demo")
        total = 12
        for i in range(1, total + 1):
            control.checkpoint()
            log.info("데모 파이프라인 진행 %d/%d", i, total)
            control.sleep(0.4)
        log.info("데모 작업 완료 / demo finished")

    # --------------------------------------------------------------- close
    def _on_close(self) -> None:
        try:
            self.controller.stop()
            self.log_panel.stop()
        finally:
            self.destroy()


def _default_nav_label(name: str) -> str:
    return {
        "account": "① 계정 · 키",
        "brand": "② 브랜드",
        "create": "③ 콘텐츠 생성",
        "schedule": "④ 예약",
        "insights": "⑤ 인사이트",
    }.get(name, name)
