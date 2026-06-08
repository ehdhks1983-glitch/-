"""
ui_motion_tab.py — ✨ 사진 → 움짤 탭
사진 1장에 카메라 움직임(켄번스/줌/패닝)을 입혀 GIF/WebP로 만든다.
"""

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from config import settings
from utils import generate_output_name
from photo_motion import MotionJob, create_motion, generate_motion_frames, EFFECTS


class MotionTab(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._image_path = ""
        self._preview_img = None
        self._preview_photo = None
        self._working = False
        self._job = None
        self._anim_imgs = []
        self._anim_idx = 0
        self._anim_playing = False
        self._anim_after = None
        self._anim_target = (480, 600)

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()

    # ──────────────────────────── 좌: 미리보기 ────────────────────────────
    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color="gray13", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=4)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        ctk.CTkButton(left, text="📂 사진 파일 열기", height=40,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._open_image
                      ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        self._name_label = ctk.CTkLabel(
            left, text="사진 1장을 넣으면 영상처럼 움직이는 움짤로 만듭니다",
            font=ctk.CTkFont(size=12), text_color="gray60")
        self._name_label.grid(row=1, column=0, sticky="ew", padx=12)

        wrap = ctk.CTkFrame(left, fg_color="black", corner_radius=8)
        wrap.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        self._preview_label = ctk.CTkLabel(
            wrap, text="📷 사진을 열면 미리보기가 표시됩니다",
            font=ctk.CTkFont(size=13), text_color="gray55")
        self._preview_label.grid(row=0, column=0, sticky="nsew")
        self._preview_label.bind("<Configure>", lambda e: self._on_preview_resize())

        self._anim_btn = ctk.CTkButton(
            left, text="▶ 효과 미리보기", height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#374151", hover_color="#4b5563",
            command=self._toggle_anim)
        self._anim_btn.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))

        self._progress = ctk.CTkProgressBar(left)
        self._progress.set(0)
        self._progress.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 2))
        self._status_label = ctk.CTkLabel(left, text="", font=ctk.CTkFont(size=12))
        self._status_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 10))

    # ──────────────────────────── 우: 설정 ────────────────────────────
    def _build_right(self):
        right = ctk.CTkScrollableFrame(self, fg_color="gray13", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=4)
        right.grid_columnconfigure(0, weight=1)
        pad = dict(padx=14, pady=(8, 0), sticky="ew")
        r = 0

        ctk.CTkLabel(right, text="🎞️ 움직임 효과",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        self._effect_var = ctk.StringVar(value=settings.get("motion_effect") or EFFECTS["ken_burns"])
        ctk.CTkOptionMenu(right, values=list(EFFECTS.values()), variable=self._effect_var,
                          font=ctk.CTkFont(size=12)).grid(row=r, column=0, **pad); r += 1

        ctk.CTkLabel(right, text="⏱️ 길이",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        self._dur_var = ctk.StringVar(value=settings.get("motion_duration") or "4초")
        ctk.CTkOptionMenu(right, values=["2초", "3초", "4초", "5초", "6초"], variable=self._dur_var,
                          font=ctk.CTkFont(size=12)).grid(row=r, column=0, **pad); r += 1

        ctk.CTkLabel(right, text="🎬 FPS (부드러움)",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        self._fps_var = ctk.StringVar(value=str(settings.get("motion_fps") or 20))
        ctk.CTkOptionMenu(right, values=["12", "15", "20", "24", "30"], variable=self._fps_var,
                          font=ctk.CTkFont(size=12)).grid(row=r, column=0, **pad); r += 1

        ctk.CTkLabel(right, text="🔍 확대량",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        _z0 = int(round((settings.get("motion_zoom") or 1.3) * 100))
        self._zoom_var = ctk.IntVar(value=min(180, max(110, _z0)))
        zf = ctk.CTkFrame(right, fg_color="transparent")
        zf.grid(row=r, column=0, **pad); r += 1
        ctk.CTkSlider(zf, from_=110, to=180, number_of_steps=70, variable=self._zoom_var,
                      command=self._on_zoom, width=150).pack(side="left", padx=(0, 8))
        self._zoom_label = ctk.CTkLabel(zf, text=f"{self._zoom_var.get() / 100:.2f}x", width=52)
        self._zoom_label.pack(side="left")

        ctk.CTkLabel(right, text="📦 출력 포맷",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        self._format_var = ctk.StringVar(value=settings.get("motion_format") or "gif")
        ff = ctk.CTkFrame(right, fg_color="transparent")
        ff.grid(row=r, column=0, **pad); r += 1
        for i, (tx, vl) in enumerate([("GIF", "gif"), ("WebP", "webp")]):
            ctk.CTkRadioButton(ff, text=tx, variable=self._format_var, value=vl,
                               font=ctk.CTkFont(size=12)).grid(row=0, column=i, padx=12)

        ctk.CTkLabel(right, text="🎚️ 화질",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        self._qmode_var = ctk.StringVar(value=settings.get("motion_quality_mode") or "🔵 균형")
        ctk.CTkSegmentedButton(right, values=["🟢 최고화질", "🔵 균형", "🟡 빠른로딩"],
                               variable=self._qmode_var,
                               font=ctk.CTkFont(size=11)).grid(row=r, column=0, **pad); r += 1

        ctk.CTkLabel(right, text="📁 저장 위치",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=r, column=0, **pad); r += 1
        self._output_dir = ctk.StringVar(value=settings.get("output_dir"))
        of = ctk.CTkFrame(right, fg_color="transparent")
        of.grid(row=r, column=0, **pad); r += 1
        of.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(of, textvariable=self._output_dir).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(of, text="...", width=36, command=self._pick_dir).grid(row=0, column=1)

        self._make_btn = ctk.CTkButton(
            right, text="✨ 움짤 만들기", height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._start)
        self._make_btn.grid(row=r, column=0, padx=14, pady=(16, 12), sticky="ew")

    def _on_zoom(self, v):
        self._zoom_label.configure(text=f"{int(float(v)) / 100:.2f}x")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self._output_dir.get() or str(Path.home()))
        if d:
            self._output_dir.set(d)
            settings.set("output_dir", d)
            settings.save()

    # ──────────────────────────── 파일 ────────────────────────────
    def _open_image(self):
        f = filedialog.askopenfilename(
            title="사진 선택",
            filetypes=[("이미지", "*.jpg *.jpeg *.png *.bmp *.webp"), ("모든 파일", "*.*")])
        if f:
            self._load_image(f)

    def add_file_from_drop(self, path):
        self._load_image(path)

    def _load_image(self, path):
        self._stop_anim()
        try:
            img = Image.open(path)
            img.load()
        except Exception:
            self._status_label.configure(text="⚠ 이미지를 열 수 없습니다", text_color="#f59e0b")
            return
        self._image_path = path
        self._preview_img = img.convert("RGB")
        self._name_label.configure(
            text=f"📷 {Path(path).name}  ({img.width}x{img.height})", text_color="white")
        self._show_preview()
        self._status_label.configure(
            text="✅ 사진 로드됨 — 효과 고르고 '움짤 만들기'", text_color="#22c55e")

    def _display_size(self, iw, ih):
        """라벨 영역에 비율 유지로 맞추는 크기 — 정적/애니 미리보기 크기를 통일"""
        lw = self._preview_label.winfo_width()
        lh = self._preview_label.winfo_height()
        if lw < 50 or lh < 50:
            lw, lh = 900, 560
        scale = min((lw - 8) / max(1, iw), (lh - 8) / max(1, ih))
        return max(2, int(iw * scale)), max(2, int(ih * scale))

    def _show_preview(self):
        if not self._preview_img:
            return
        try:
            iw, ih = self._preview_img.size
            tw, th = self._display_size(iw, ih)
            im = self._preview_img.resize((tw, th), Image.LANCZOS)
            self._preview_photo = ctk.CTkImage(light_image=im, dark_image=im, size=(tw, th))
            self._preview_label.configure(image=self._preview_photo, text="")
        except Exception:
            pass

    # ──────────────────────────── 변환 ────────────────────────────
    def _on_preview_resize(self):
        if not self._anim_playing:
            self._show_preview()

    def _toggle_anim(self):
        if not self._image_path or not self._preview_img:
            self._status_label.configure(text="⚠ 먼저 사진을 선택하세요", text_color="#f59e0b")
            return
        if self._anim_playing:
            self._stop_anim()
        else:
            iw, ih = self._preview_img.size
            self._anim_target = self._display_size(iw, ih)  # 정적 미리보기와 같은 크기로
            self._anim_btn.configure(text="⏳ 미리보기 생성 중...", state="disabled")
            threading.Thread(target=self._gen_anim, daemon=True).start()

    def _gen_anim(self):
        """현재 설정으로 저해상도 모션 프레임 생성 (스레드) → 메인에서 재생"""
        try:
            label = self._effect_var.get()
            eff = next((k for k, v in EFFECTS.items() if v == label), "ken_burns")
            try:
                dur = float(self._dur_var.get().replace("초", "").strip())
            except ValueError:
                dur = 4.0
            fps = int(self._fps_var.get())
            zoom = self._zoom_var.get() / 100.0
            n = max(2, min(120, int(round(dur * fps))))  # 미리보기는 최대 120프레임
            tw, th = self._anim_target
            tw = max(2, tw - tw % 2); th = max(2, th - th % 2)
            frames = generate_motion_frames(self._preview_img, eff, n, zoom, tw, th)
            delay = max(30, int(dur * 1000 / max(1, n)))  # 실제 길이에 맞춰 루프 재생
            self.after(0, lambda fr=frames, d=delay: self._begin_anim(fr, d))
        except Exception as e:
            self.after(0, lambda e=e: (
                self._anim_btn.configure(text="▶ 효과 미리보기", state="normal"),
                self._status_label.configure(text=f"미리보기 실패: {e}", text_color="#ef4444"),
            ))

    def _begin_anim(self, frames, delay):
        # 프레임이 이미 정적 미리보기와 같은 크기 → 그대로 표시 (크기/위치 안 바뀜)
        self._anim_imgs = [ctk.CTkImage(light_image=f, dark_image=f, size=f.size) for f in frames]
        self._anim_idx = 0
        self._anim_playing = True
        self._anim_delay = delay
        self._anim_btn.configure(text="⏸ 미리보기 정지", state="normal")
        self._status_label.configure(text="▶ 미리보기 재생 중 (실제 결과와 동일한 움직임)", text_color="#22c55e")
        self._play_anim()

    def _play_anim(self):
        if not self._anim_playing or not self._anim_imgs:
            return
        i = self._anim_idx % len(self._anim_imgs)
        self._preview_label.configure(image=self._anim_imgs[i], text="")
        self._anim_idx = (i + 1) % len(self._anim_imgs)
        self._anim_after = self.after(self._anim_delay, self._play_anim)

    def _stop_anim(self):
        self._anim_playing = False
        if self._anim_after:
            try:
                self.after_cancel(self._anim_after)
            except Exception:
                pass
            self._anim_after = None
        self._anim_imgs = []
        try:
            self._anim_btn.configure(text="▶ 효과 미리보기", state="normal")
        except Exception:
            pass
        self._show_preview()

    def _build_job(self) -> MotionJob:
        j = MotionJob()
        j.input_path = self._image_path
        label = self._effect_var.get()
        j.effect = next((k for k, v in EFFECTS.items() if v == label), "ken_burns")
        try:
            j.duration = float(self._dur_var.get().replace("초", "").strip())
        except ValueError:
            j.duration = 4.0
        j.fps = int(self._fps_var.get())
        j.zoom = self._zoom_var.get() / 100.0
        j.output_format = self._format_var.get()

        qm = self._qmode_var.get()
        if "최고" in qm:
            j.quality_mode, j.gif_lossy = "best", 0
        elif "빠른" in qm:
            j.quality_mode, j.gif_lossy = "fast", 60
            j.fps = min(j.fps, 15)
        else:
            j.quality_mode, j.gif_lossy = "balanced", 30

        base = Path(self._image_path).stem + "_motion"
        j.output_path = generate_output_name(base, j.output_format, self._output_dir.get())
        return j

    def _start(self):
        if self._working:
            return
        if not self._image_path or not Path(self._image_path).exists():
            self._status_label.configure(text="⚠ 먼저 사진을 선택하세요", text_color="#f59e0b")
            return
        self._stop_anim()

        settings.set("motion_effect", self._effect_var.get())
        settings.set("motion_duration", self._dur_var.get())
        settings.set("motion_fps", int(self._fps_var.get()))
        settings.set("motion_zoom", round(self._zoom_var.get() / 100.0, 2))
        settings.set("motion_format", self._format_var.get())
        settings.set("motion_quality_mode", self._qmode_var.get())
        settings.save()

        self._job = self._build_job()
        self._working = True
        self._make_btn.configure(state="disabled", text="⏳ 만드는 중...")
        self._progress.set(0)
        self._status_label.configure(text="시작...", text_color="white")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        def cb(p, m):
            self.after(0, lambda p=p, m=m: (
                self._progress.set(max(0.0, min(1.0, p / 100.0))),
                self._status_label.configure(text=m),
            ))
        try:
            result = create_motion(self._job, on_progress=cb)
        except Exception as e:
            result = None
            self.after(0, lambda e=e: self._status_label.configure(
                text=f"❌ 오류: {e}", text_color="#ef4444"))
        self.after(0, lambda: self._done(result))

    def _done(self, result):
        self._working = False
        self._make_btn.configure(state="normal", text="✨ 움짤 만들기")
        if result and Path(result).exists():
            self._status_label.configure(
                text=f"✅ 완료! {Path(result).name}", text_color="#22c55e")
