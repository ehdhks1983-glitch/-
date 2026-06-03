"""Scheduling tab: queue posts for future auto-publish (spec Stage 6).

Shows the mandatory notice that scheduling only fires while the PC + program run.
The scheduler loop runs on the shared controller (Pause/Stop apply).  Scheduled
posts are treated as pre-approved (queuing IS the approval) and run the full
generate -> host -> publish flow when due, subject to the daily guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from tkinter import filedialog
from typing import List

import customtkinter as ctk

import config
from core.app_services import build_pipeline
from core.logging_setup import get_logger
from core.publish_flow import ImageSource
from core.scheduler import Scheduler
from ui.widgets import Toast

log = get_logger("ui.schedule")

MEDIA_TYPES = ("image", "carousel", "reels")
IMAGE_MODES = ("AI 생성", "직접 업로드")


class ScheduleTab(ctk.CTkFrame):
    def __init__(self, master, store, controller) -> None:
        super().__init__(master)
        self.store = store
        self.controller = controller
        self.scheduler = Scheduler()
        self._upload_paths: List[str] = []
        self._build()
        self.refresh_list()

    # ---------------------------------------------------------------- build
    def _build(self) -> None:
        ctk.CTkLabel(self, text="예약 / 스케줄러", anchor="w",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(fill="x", padx=16, pady=(16, 0))

        # Mandatory always-visible notice.
        notice = ctk.CTkLabel(self, text="🖥  " + config.SCHEDULE_REQUIRES_RUNNING_NOTICE,
                              anchor="w", text_color="#fbbf24",
                              fg_color="#3b2f12", corner_radius=6)
        notice.pack(fill="x", padx=16, pady=(6, 10), ipady=6)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=4)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # --- left: add form ---
        form = ctk.CTkScrollableFrame(body, label_text="예약 추가")
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        soon = datetime.now() + timedelta(hours=1)
        self._field(form, "날짜 (YYYY-MM-DD)")
        self.date_entry = ctk.CTkEntry(form)
        self.date_entry.insert(0, soon.strftime("%Y-%m-%d"))
        self.date_entry.pack(fill="x", padx=8, pady=(0, 8))

        self._field(form, "시간 (HH:MM)")
        self.time_entry = ctk.CTkEntry(form)
        self.time_entry.insert(0, soon.strftime("%H:%M"))
        self.time_entry.pack(fill="x", padx=8, pady=(0, 8))

        self._field(form, "주제 / Topic")
        self.topic_entry = ctk.CTkEntry(form, placeholder_text="예: 주말 추천 루틴")
        self.topic_entry.pack(fill="x", padx=8, pady=(0, 8))

        self._field(form, "포맷 / Format")
        self.media_var = ctk.StringVar(value="image")
        ctk.CTkOptionMenu(form, values=list(MEDIA_TYPES), variable=self.media_var).pack(
            fill="x", padx=8, pady=(0, 8))

        self._field(form, "이미지 소스")
        self.mode_var = ctk.StringVar(value=IMAGE_MODES[0])
        ctk.CTkOptionMenu(form, values=list(IMAGE_MODES), variable=self.mode_var,
                          command=lambda *_: self._on_mode_change()).pack(fill="x", padx=8, pady=(0, 8))
        self.ai_prompt = ctk.CTkEntry(form, placeholder_text="이미지 프롬프트(비우면 주제 사용)")
        self.upload_btn = ctk.CTkButton(form, text="이미지 파일 선택…", command=self._pick_files)
        self.files_label = ctk.CTkLabel(form, text="선택된 파일 없음", anchor="w", text_color="#8b95a7")

        ctk.CTkButton(form, text="＋ 예약 추가", command=self._on_add).pack(fill="x", padx=8, pady=(10, 8))

        # --- right: queue list + scheduler control ---
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(head, text="예약 큐", anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self.run_btn = ctk.CTkButton(head, text="스케줄러 시작", width=120, command=self._toggle_scheduler)
        self.run_btn.pack(side="right")
        self.list_frame = ctk.CTkScrollableFrame(right)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self._on_mode_change()

    @staticmethod
    def _field(parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w").pack(fill="x", padx=8, pady=(8, 0))

    def _on_mode_change(self) -> None:
        if self.mode_var.get() == IMAGE_MODES[0]:
            self.ai_prompt.pack(fill="x", padx=8, pady=(0, 8))
            self.upload_btn.pack_forget()
            self.files_label.pack_forget()
        else:
            self.ai_prompt.pack_forget()
            self.upload_btn.pack(fill="x", padx=8, pady=(0, 4))
            self.files_label.pack(fill="x", padx=8, pady=(0, 8))

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="이미지 선택",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.webp"), ("모든 파일", "*.*")])
        if paths:
            self._upload_paths = list(paths)
            self.files_label.configure(text=f"{len(self._upload_paths)}개 파일 선택됨")

    # ---------------------------------------------------------------- add
    def _collect_sources(self, media_type: str) -> List[ImageSource]:
        if self.mode_var.get() == IMAGE_MODES[0]:
            prompt = self.ai_prompt.get().strip()
            n = 3 if media_type == "carousel" else 1
            return [ImageSource("ai", prompt=prompt) for _ in range(n)]
        return [ImageSource("upload", path=p) for p in self._upload_paths]

    def _on_add(self) -> None:
        topic = self.topic_entry.get().strip()
        if not topic:
            Toast(self.winfo_toplevel(), "주제를 입력하세요", kind="warn")
            return
        try:
            when = datetime.strptime(
                f"{self.date_entry.get().strip()} {self.time_entry.get().strip()}",
                "%Y-%m-%d %H:%M")
        except ValueError:
            Toast(self.winfo_toplevel(), "날짜/시간 형식이 올바르지 않습니다 (YYYY-MM-DD HH:MM)", kind="error")
            return
        media_type = self.media_var.get()
        sources = self._collect_sources(media_type)
        if self.mode_var.get() == IMAGE_MODES[1] and not self._upload_paths:
            Toast(self.winfo_toplevel(), "이미지 파일을 선택하세요", kind="warn")
            return
        post = self.scheduler.add(when, topic, media_type, sources)
        Toast(self.winfo_toplevel(),
              f"예약됨 · 실제 발행 ~{post.effective_at.strftime('%m-%d %H:%M')} (지터 적용)",
              kind="success")
        self.refresh_list()

    # ---------------------------------------------------------------- list
    def refresh_list(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        posts = self.scheduler.all()
        if not posts:
            ctk.CTkLabel(self.list_frame, text="예약된 게시물이 없습니다.", text_color="#8b95a7").pack(
                anchor="w", padx=8, pady=8)
            return
        colors = {"pending": "#3b82f6", "done": "#16a34a", "failed": "#dc2626"}
        for p in posts:
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", padx=4, pady=3)
            txt = (f"{p.effective_at.strftime('%m-%d %H:%M')}  ·  {p.media_type}  ·  {p.topic}"
                   f"   [{p.status}]")
            ctk.CTkLabel(row, text=txt, anchor="w", text_color=colors.get(p.status, "#cbd5e1")).pack(
                side="left", padx=8, pady=4, fill="x", expand=True)
            ctk.CTkButton(row, text="삭제", width=56, fg_color="#7f1d1d", hover_color="#991b1b",
                          command=lambda pid=p.id: self._remove(pid)).pack(side="right", padx=6)

    def _remove(self, post_id: str) -> None:
        self.scheduler.remove(post_id)
        self.refresh_list()

    # ---------------------------------------------------------------- run
    def refresh_status(self) -> None:
        self.refresh_list()
        self.run_btn.configure(text="스케줄러 중지" if self.controller.is_active else "스케줄러 시작")

    def primary_action(self) -> None:
        # Global "시작" while on this tab starts the scheduler (only when idle;
        # _on_start guards against re-entry, so this never double-starts).
        self._toggle_scheduler()

    def _toggle_scheduler(self) -> None:
        if self.controller.is_active:
            self.controller.stop()
            Toast(self.winfo_toplevel(), "스케줄러 중지 요청", kind="info")
            return
        if not self.store.is_configured_for_publish():
            Toast(self.winfo_toplevel(), "계정 탭에서 토큰/User ID를 먼저 입력하세요", kind="error")
            return
        self.controller.start(self.scheduler.run_forever, self._runner, name="scheduler")
        Toast(self.winfo_toplevel(), "스케줄러 시작 · 도래 시 자동 발행", kind="success")
        self.run_btn.configure(text="스케줄러 중지")

    def _runner(self, post) -> None:
        pipeline = build_pipeline(self.store)
        if pipeline.api is None:
            raise RuntimeError("토큰/User ID 미설정")
        prepared = pipeline.prepare(post.topic, post.media_type, post.image_sources)
        pipeline.publish(prepared)
        self.after(0, self.refresh_list)
