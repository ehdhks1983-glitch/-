"""
watermark_dialog.py - 워터마크 설정 창
블로그 ID/로고를 모든 변환 결과에 자동 삽입하는 설정 + 실시간 미리보기
"""

import customtkinter as ctk
from PIL import Image, ImageDraw

from watermark import (
    watermark, apply_to_frame,
    POSITION_NAMES, KEY_TO_NAME, MODE_NAMES, NAME_TO_MODE,
)

TEXT_COLORS = {"⬜ 흰색": "#FFFFFF", "⬛ 검정": "#000000", "🟨 노랑": "#FFFF00", "🟥 빨강": "#FF0000"}
COLOR_TO_NAME = {v: k for k, v in TEXT_COLORS.items()}


class WatermarkDialog(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("💧 워터마크 설정")
        self.geometry("560x660")
        self.resizable(False, False)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 560) // 2
        y = (self.winfo_screenheight() - 660) // 2
        self.geometry(f"+{x}+{y}")
        self.transient(master)
        self.grab_set()
        self._preview_img = None
        self._build()
        self._refresh()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        # 좌: 설정
        s = ctk.CTkScrollableFrame(self, fg_color="gray12")
        s.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=10)
        pad = {"padx": 12, "pady": (6, 2), "sticky": "ew"}

        ctk.CTkLabel(s, text="모든 변환 결과에 자동으로 워터마크를 넣습니다",
                     font=ctk.CTkFont(size=12), text_color="gray60",
                     wraplength=250, justify="left").grid(row=0, column=0, **pad)

        self._enabled = ctk.BooleanVar(value=watermark.get("enabled"))
        ctk.CTkSwitch(s, text="워터마크 사용", variable=self._enabled,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._refresh).grid(row=1, column=0, **pad)

        ctk.CTkLabel(s, text="종류", font=ctk.CTkFont(size=12)).grid(row=2, column=0, **pad)
        self._mode = ctk.StringVar(value=NAME_TO_MODE.get(watermark.get("mode"), "텍스트"))
        ctk.CTkOptionMenu(s, values=list(MODE_NAMES.keys()), variable=self._mode,
                          command=lambda _=None: self._refresh()).grid(row=3, column=0, **pad)

        ctk.CTkLabel(s, text="📝 텍스트 (예: @블로그아이디)",
                     font=ctk.CTkFont(size=12)).grid(row=4, column=0, **pad)
        self._text = ctk.CTkEntry(s, font=ctk.CTkFont(size=13), height=32,
                                  placeholder_text="@myblog")
        self._text.insert(0, watermark.get("text") or "")
        self._text.grid(row=5, column=0, **pad)
        self._text.bind("<KeyRelease>", lambda e: self._refresh())

        ctk.CTkLabel(s, text="글자 색", font=ctk.CTkFont(size=12)).grid(row=6, column=0, **pad)
        self._color = ctk.StringVar(value=COLOR_TO_NAME.get(watermark.get("text_color"), "⬜ 흰색"))
        ctk.CTkOptionMenu(s, values=list(TEXT_COLORS.keys()), variable=self._color,
                          command=lambda _=None: self._refresh()).grid(row=7, column=0, **pad)

        ctk.CTkLabel(s, text="🖼 로고 이미지 (PNG 권장)",
                     font=ctk.CTkFont(size=12)).grid(row=8, column=0, **pad)
        logo_frame = ctk.CTkFrame(s, fg_color="transparent")
        logo_frame.grid(row=9, column=0, **pad)
        ctk.CTkButton(logo_frame, text="로고 선택", width=90, height=28,
                      command=self._pick_logo).pack(side="left", padx=(0, 6))
        self._logo_label = ctk.CTkLabel(logo_frame, text="없음", font=ctk.CTkFont(size=11),
                                        text_color="gray50")
        self._logo_label.pack(side="left", fill="x", expand=True)
        if watermark.get("image_path"):
            from pathlib import Path
            self._logo_label.configure(text=Path(watermark.get("image_path")).name, text_color="white")

        ctk.CTkLabel(s, text="위치", font=ctk.CTkFont(size=12)).grid(row=10, column=0, **pad)
        self._pos = ctk.StringVar(value=KEY_TO_NAME.get(watermark.get("position"), "우측 하단"))
        ctk.CTkOptionMenu(s, values=list(POSITION_NAMES.keys()), variable=self._pos,
                          command=lambda _=None: self._refresh()).grid(row=11, column=0, **pad)

        self._size = self._slider(s, 12, "로고 크기", 5, 50, watermark.get("scale"), "%")
        self._opacity = self._slider(s, 14, "투명도", 10, 100, watermark.get("opacity"), "%")
        self._margin = self._slider(s, 16, "여백", 0, 12, watermark.get("margin"), "%")

        # 우: 미리보기 + 버튼
        right = ctk.CTkFrame(self, fg_color="gray12", width=250)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 10), pady=10)
        right.grid_propagate(False)
        ctk.CTkLabel(right, text="미리보기", font=ctk.CTkFont(size=12),
                     text_color="gray60").pack(pady=(10, 4))
        self._preview = ctk.CTkLabel(right, text="", width=220, height=360)
        self._preview.pack(padx=10, pady=4)
        ctk.CTkButton(right, text="💾 저장하고 닫기", height=40,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color="#2563eb", hover_color="#1d4ed8",
                      command=self._save).pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        ctk.CTkButton(right, text="닫기", height=30, fg_color="gray30",
                      command=self.destroy).pack(side="bottom", fill="x", padx=10, pady=2)

    def _slider(self, parent, row, label, lo, hi, val, unit):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, padx=12, pady=(6, 0), sticky="ew")
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=12), width=70, anchor="w").pack(side="left")
        var = ctk.IntVar(value=int(val))
        lbl = ctk.CTkLabel(f, text=f"{int(val)}{unit}", font=ctk.CTkFont(size=12), width=45)
        slider = ctk.CTkSlider(f, from_=lo, to=hi, variable=var, width=120,
                               command=lambda _=None, l=lbl, v=var, u=unit: (
                                   l.configure(text=f"{v.get()}{u}"), self._refresh()))
        slider.pack(side="left", padx=6)
        lbl.pack(side="left")
        return var

    def _pick_logo(self):
        from tkinter import filedialog
        from pathlib import Path
        f = filedialog.askopenfilename(title="로고 이미지 선택",
                                       filetypes=[("이미지", "*.png *.jpg *.jpeg *.webp"), ("모든 파일", "*.*")])
        if f:
            watermark.set("image_path", f)
            self._logo_label.configure(text=Path(f).name, text_color="white")
            self._refresh()

    def _sync(self):
        watermark.set("enabled", self._enabled.get())
        watermark.set("mode", NAME_TO_MODE.get(self._mode.get(), "text"))
        watermark.set("text", self._text.get())
        watermark.set("text_color", TEXT_COLORS.get(self._color.get(), "#FFFFFF"))
        watermark.set("position", POSITION_NAMES.get(self._pos.get(), "br"))
        watermark.set("scale", self._size.get())
        watermark.set("opacity", self._opacity.get())
        watermark.set("margin", self._margin.get())

    def _make_sample(self) -> Image.Image:
        img = Image.new("RGB", (360, 600), (60, 120, 170))
        d = ImageDraw.Draw(img)
        for i in range(0, 600, 40):
            d.line([(0, i), (360, i)], fill=(80, 140, 190), width=1)
        d.rectangle([60, 240, 300, 360], fill=(110, 160, 200))
        d.text((150, 295), "샘플", fill="white")
        return img

    def _refresh(self):
        self._sync()
        sample = self._make_sample()
        prev = watermark.get("enabled")
        watermark.set("enabled", True)  # 미리보기는 항상 보이게
        try:
            shown = apply_to_frame(sample)
        finally:
            watermark.set("enabled", prev)
        shown.thumbnail((220, 360), Image.LANCZOS)
        self._preview_img = ctk.CTkImage(light_image=shown, dark_image=shown,
                                         size=(shown.width, shown.height))
        self._preview.configure(image=self._preview_img, text="")

    def _save(self):
        self._sync()
        watermark.save()
        self.destroy()
