"""Content creation tab: generate -> preview -> approve -> publish (spec Stage 5).

The mandatory review step lives here: nothing is posted until the user inspects
the caption + image + hashtags and clicks "승인 후 게시".  Generation and
publishing run on the shared AutomationController so the global Pause/Stop and
live-log apply.
"""

from __future__ import annotations

from tkinter import filedialog
from typing import List, Optional

import customtkinter as ctk
from PIL import Image

from core.app_services import build_pipeline, build_token_manager
from core.logging_setup import get_logger
from core.publish_flow import ImageSource, PreparedPost
from core.settings_store import SettingsStore
from ui.widgets import Toast

log = get_logger("ui.create")

MEDIA_TYPES = ("image", "carousel", "reels")
IMAGE_MODES = ("AI 생성", "직접 업로드")


class CreateTab(ctk.CTkFrame):
    def __init__(self, master, store: SettingsStore, controller) -> None:
        super().__init__(master)
        self.store = store
        self.controller = controller
        self._prepared: Optional[PreparedPost] = None
        self._pipeline = None
        self._upload_paths: List[str] = []
        self._thumb = None
        self._build()
        self.refresh_status()

    # ---------------------------------------------------------------- build
    def _build(self) -> None:
        ctk.CTkLabel(self, text="콘텐츠 생성 · 미리보기 · 승인", anchor="w",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(fill="x", padx=16, pady=(16, 0))
        self.status_label = ctk.CTkLabel(self, text="", anchor="w", text_color="#8b95a7")
        self.status_label.pack(fill="x", padx=16, pady=(2, 8))

        # Actions pinned to the bottom first, so the mandatory "approve" button
        # is never squeezed off-screen by the expanding body below.
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=16, pady=(0, 14))
        self.gen_btn = ctk.CTkButton(actions, text="① 생성 & 미리보기", command=self.primary_action)
        self.pub_btn = ctk.CTkButton(actions, text="② 승인 후 게시", state="disabled",
                                     fg_color="#15803d", hover_color="#166534", command=self._on_publish)
        self.gen_btn.pack(side="left", padx=(0, 8))
        self.pub_btn.pack(side="left")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=4)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # --- left: inputs ---
        form = ctk.CTkScrollableFrame(body, label_text="입력")
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._row(form, "주제 / Topic")
        self.topic_entry = ctk.CTkEntry(form, placeholder_text="예: 아침 루틴 만들기")
        self.topic_entry.pack(fill="x", padx=8, pady=(0, 8))

        self._row(form, "포맷 / Format")
        self.media_var = ctk.StringVar(value="image")
        ctk.CTkOptionMenu(form, values=list(MEDIA_TYPES), variable=self.media_var,
                          command=lambda *_: self._on_mode_change()).pack(fill="x", padx=8, pady=(0, 8))

        self._row(form, "이미지 소스")
        self.mode_var = ctk.StringVar(value=IMAGE_MODES[0])
        ctk.CTkOptionMenu(form, values=list(IMAGE_MODES), variable=self.mode_var,
                          command=lambda *_: self._on_mode_change()).pack(fill="x", padx=8, pady=(0, 8))

        self.ai_prompt = ctk.CTkEntry(form, placeholder_text="이미지 프롬프트(비우면 주제 사용)")
        self.ai_prompt.pack(fill="x", padx=8, pady=(0, 8))

        self.upload_btn = ctk.CTkButton(form, text="이미지 파일 선택…", command=self._pick_files)
        self.files_label = ctk.CTkLabel(form, text="선택된 파일 없음", anchor="w", text_color="#8b95a7")

        self._row(form, "캐러셀 장수")
        self.count_var = ctk.StringVar(value="3")
        self.count_menu = ctk.CTkOptionMenu(form, values=[str(i) for i in range(2, 11)],
                                            variable=self.count_var)

        # --- right: preview ---
        preview = ctk.CTkFrame(body)
        preview.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(preview, text="미리보기 / Preview", anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=12, pady=(10, 4))
        self.image_label = ctk.CTkLabel(preview, text="(이미지 없음)", width=240, height=240,
                                        fg_color="#1f2430", corner_radius=8)
        self.image_label.pack(padx=12, pady=6)
        self.caption_box = ctk.CTkTextbox(preview, height=160, wrap="word")
        self.caption_box.configure(state="disabled")
        self.caption_box.pack(fill="both", expand=True, padx=12, pady=6)
        self.warn_label = ctk.CTkLabel(preview, text="", anchor="w", text_color="#d97706",
                                       wraplength=360, justify="left")
        self.warn_label.pack(fill="x", padx=12, pady=(0, 8))

        self._on_mode_change()

    @staticmethod
    def _row(parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w").pack(fill="x", padx=8, pady=(8, 0))

    # ---------------------------------------------------------------- status
    def refresh_status(self) -> None:
        store = self.store
        has_keys = store.is_configured_for_publish()
        tm = build_token_manager(store)
        _, days = tm.status_summary()
        guard_txt = ""
        try:
            from core.app_services import build_guard
            g = build_guard(store)
            guard_txt = f" · 오늘 남은 게시 {g.remaining()}/{g.max}"
        except Exception:  # pragma: no cover
            pass
        if not has_keys:
            msg = "⚠ 계정 탭에서 액세스 토큰과 User ID를 먼저 입력하세요."
        else:
            exp = f"토큰 만료 {days:.0f}일 후" if days is not None else "토큰 만료일 미기록"
            msg = f"게시 준비됨 · {exp}{guard_txt}"
        self.status_label.configure(text=msg)

    def _on_mode_change(self) -> None:
        is_ai = self.mode_var.get() == IMAGE_MODES[0]
        is_carousel = self.media_var.get() == "carousel"
        # toggle AI prompt vs file picker
        if is_ai:
            self.ai_prompt.pack(fill="x", padx=8, pady=(0, 8))
            self.upload_btn.pack_forget()
            self.files_label.pack_forget()
        else:
            self.ai_prompt.pack_forget()
            self.upload_btn.pack(fill="x", padx=8, pady=(0, 4))
            self.files_label.pack(fill="x", padx=8, pady=(0, 8))
        # carousel count only relevant for AI carousels
        if is_carousel and is_ai:
            self.count_menu.pack(fill="x", padx=8, pady=(0, 8))
        else:
            self.count_menu.pack_forget()

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="이미지 선택",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.webp"), ("모든 파일", "*.*")],
        )
        if paths:
            self._upload_paths = list(paths)
            self.files_label.configure(text=f"{len(self._upload_paths)}개 파일 선택됨")

    def _collect_sources(self, media_type: str) -> List[ImageSource]:
        if self.mode_var.get() == IMAGE_MODES[0]:  # AI
            prompt = self.ai_prompt.get().strip()
            n = int(self.count_var.get()) if media_type == "carousel" else 1
            return [ImageSource("ai", prompt=prompt) for _ in range(n)]
        return [ImageSource("upload", path=p) for p in self._upload_paths]

    # ---------------------------------------------------------------- generate
    def primary_action(self) -> None:
        if self.controller.is_active:
            return
        topic = self.topic_entry.get().strip()
        if not topic:
            Toast(self.winfo_toplevel(), "주제를 입력하세요", kind="warn")
            return
        media_type = self.media_var.get()
        sources = self._collect_sources(media_type)
        if not sources or (self.mode_var.get() == IMAGE_MODES[1] and not self._upload_paths):
            Toast(self.winfo_toplevel(), "이미지 소스를 지정하세요", kind="warn")
            return
        self._pipeline = build_pipeline(self.store)
        self._set_generating(True)
        self.controller.start(self._do_prepare, self._pipeline, topic, media_type, sources,
                              on_done=self._on_prepared, on_error=self._on_job_error)

    def _do_prepare(self, control, pipeline, topic, media_type, sources):
        return pipeline.prepare(topic, media_type, sources, control=control)

    def _on_prepared(self, prepared: PreparedPost) -> None:
        self.after(0, self._show_preview, prepared)

    def _show_preview(self, prepared: PreparedPost) -> None:
        self._prepared = prepared
        self._set_generating(False)
        self.caption_box.configure(state="normal")
        self.caption_box.delete("1.0", "end")
        self.caption_box.insert("1.0", prepared.caption)
        self.caption_box.configure(state="disabled")
        if prepared.local_paths:
            try:
                img = Image.open(prepared.local_paths[0])
                img.thumbnail((240, 240))
                self._thumb = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.image_label.configure(image=self._thumb, text="")
            except Exception as exc:  # pragma: no cover
                log.warning("미리보기 이미지 로드 실패: %s", exc)
        warns = "\n".join(prepared.draft.warnings)
        self.warn_label.configure(text=("⚠ " + warns) if warns else "")
        self.pub_btn.configure(state="normal")
        Toast(self.winfo_toplevel(), "미리보기 생성 완료 · 검토 후 게시하세요", kind="success")

    # ---------------------------------------------------------------- publish
    def _on_publish(self) -> None:
        if not self._prepared or self._pipeline is None or self.controller.is_active:
            return
        if self._pipeline.api is None:
            Toast(self.winfo_toplevel(), "토큰/User ID가 없어 게시할 수 없습니다", kind="error")
            return
        self.pub_btn.configure(state="disabled")
        self.controller.start(self._do_publish, self._pipeline, self._prepared,
                              on_done=self._on_published, on_error=self._on_job_error)

    def _do_publish(self, control, pipeline, prepared):
        return pipeline.publish(prepared, control=control)

    def _on_published(self, result) -> None:
        def show():
            link = result.permalink or result.media_id
            Toast(self.winfo_toplevel(), f"게시 완료! {link}", kind="success", duration_ms=5000)
            self.refresh_status()
            self._prepared = None
        self.after(0, show)

    def _on_job_error(self, exc: BaseException) -> None:
        from core.errors import humanize
        msg = humanize(exc)

        def show():
            self._set_generating(False)
            self.pub_btn.configure(state="normal" if self._prepared else "disabled")
            Toast(self.winfo_toplevel(), msg, kind="error", duration_ms=6000)
        self.after(0, show)

    def _set_generating(self, busy: bool) -> None:
        self.gen_btn.configure(state="disabled" if busy else "normal")
