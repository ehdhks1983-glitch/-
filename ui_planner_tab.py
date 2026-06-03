"""
ui_planner_tab.py - 영상 기획 디렉터 탭
목적·타겟·상품·문제·메시지를 입력하면 후킹·구조·대본·장면표·자막·업로드문구·검수까지
한 번에 기획서로 뽑아준다. (오프라인, API 불필요)
"""

import os
from pathlib import Path

import customtkinter as ctk

from config import settings
import content_planner as cp


class PlannerTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._problem_idx = 0
        self._last_text = ""
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=340)
        self.grid_columnconfigure(1, weight=1, minsize=380)
        self.grid_rowconfigure(0, weight=1)
        self._build_inputs()
        self._build_output()

    # ─── 좌: 입력 ───
    def _build_inputs(self):
        left = ctk.CTkScrollableFrame(self, fg_color="gray14", corner_radius=10, width=330)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        pad = {"padx": 12, "pady": (6, 1), "sticky": "ew"}
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="🎬 영상 기획 디렉터",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, **pad)
        ctk.CTkLabel(left, text="입력만 채우면 후킹·대본·자막·업로드문구·검수까지 한 번에",
                     font=ctk.CTkFont(size=11), text_color="gray55",
                     wraplength=300, justify="left").grid(row=1, column=0, **pad)

        ctk.CTkLabel(left, text="① 영상 목적", font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, **pad)
        self._purpose = ctk.StringVar(value="문의 유도")
        ctk.CTkOptionMenu(left, values=cp.PURPOSES, variable=self._purpose,
                          font=ctk.CTkFont(size=12)).grid(row=3, column=0, **pad)

        ctk.CTkLabel(left, text="② 타겟", font=ctk.CTkFont(size=12, weight="bold")).grid(row=4, column=0, **pad)
        self._target = ctk.StringVar(value="자영업자")
        ctk.CTkOptionMenu(left, values=cp.TARGETS, variable=self._target,
                          font=ctk.CTkFont(size=12)).grid(row=5, column=0, **pad)
        self._target_custom = ctk.CTkEntry(left, font=ctk.CTkFont(size=12), height=28,
                                           placeholder_text="또는 직접 입력 (선택)")
        self._target_custom.grid(row=6, column=0, **pad)

        ctk.CTkLabel(left, text="③ 상품/서비스", font=ctk.CTkFont(size=12, weight="bold")).grid(row=7, column=0, **pad)
        self._product = ctk.CTkEntry(left, font=ctk.CTkFont(size=12), height=30,
                                     placeholder_text="예: 블로그 자동화봇")
        self._product.grid(row=8, column=0, **pad)

        prob_h = ctk.CTkFrame(left, fg_color="transparent")
        prob_h.grid(row=9, column=0, **pad)
        ctk.CTkLabel(prob_h, text="④ 고객 문제", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(prob_h, text="💡 예시", width=60, height=24, font=ctk.CTkFont(size=11),
                      fg_color="gray30", command=self._fill_problem).pack(side="right")
        self._problem = ctk.CTkTextbox(left, height=50, font=ctk.CTkFont(size=12), wrap="word")
        self._problem.grid(row=10, column=0, **pad)

        ctk.CTkLabel(left, text="⑤ 핵심 메시지 (딱 하나)", font=ctk.CTkFont(size=12, weight="bold")).grid(row=11, column=0, **pad)
        self._message = ctk.CTkEntry(left, font=ctk.CTkFont(size=12), height=30,
                                     placeholder_text="비우면 자동 생성")
        self._message.grid(row=12, column=0, **pad)

        ctk.CTkLabel(left, text="⑥ 흔한 오해 (선택)", font=ctk.CTkFont(size=12, weight="bold")).grid(row=13, column=0, **pad)
        self._misconception = ctk.CTkEntry(left, font=ctk.CTkFont(size=12), height=28,
                                           placeholder_text="예: 글쓰기 실력")
        self._misconception.grid(row=14, column=0, **pad)

        ctk.CTkLabel(left, text="⑦ 후킹 유형 / 길이", font=ctk.CTkFont(size=12, weight="bold")).grid(row=15, column=0, **pad)
        row16 = ctk.CTkFrame(left, fg_color="transparent")
        row16.grid(row=16, column=0, **pad)
        self._hook = ctk.StringVar(value="반전형")
        ctk.CTkOptionMenu(row16, values=cp.HOOK_TYPES, variable=self._hook, width=120,
                          font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self._length = ctk.StringVar(value="쇼츠 30초")
        ctk.CTkOptionMenu(row16, values=cp.LENGTHS, variable=self._length, width=110,
                          font=ctk.CTkFont(size=12)).pack(side="left")

        ctk.CTkButton(left, text="🎬 전체 기획서 생성", height=44,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      fg_color="#7c3aed", hover_color="#6d28d9",
                      command=self._generate).grid(row=17, column=0, padx=12, pady=(12, 12), sticky="ew")

    # ─── 우: 결과 ───
    def _build_output(self):
        right = ctk.CTkFrame(self, fg_color="gray14", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ctk.CTkLabel(head, text="📋 기획서 결과", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="💾 저장", width=70, height=28, font=ctk.CTkFont(size=12),
                      fg_color="gray30", command=self._save).pack(side="right", padx=2)
        ctk.CTkButton(head, text="📋 복사", width=70, height=28, font=ctk.CTkFont(size=12),
                      command=self._copy).pack(side="right", padx=2)

        self._out = ctk.CTkTextbox(right, font=ctk.CTkFont(size=12, family="맑은 고딕"), wrap="word")
        self._out.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self._out.insert("1.0", "왼쪽 입력을 채우고 '🎬 전체 기획서 생성'을 눌러주세요.\n\n"
                                "팁: 상품/서비스와 고객 문제만 잘 적어도 후킹·대본·자막·업로드문구·검수까지 한 번에 나옵니다.")

        self._status = ctk.CTkLabel(right, text="", font=ctk.CTkFont(size=11), text_color="gray55")
        self._status.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 8))

    # ─── 동작 ───
    def _get_target(self) -> str:
        c = self._target_custom.get().strip()
        return c if c else self._target.get()

    def _fill_problem(self):
        target = self._get_target()
        sug = cp.suggest_problems(target)
        if not sug:
            return
        text = sug[self._problem_idx % len(sug)]
        self._problem_idx += 1
        self._problem.delete("1.0", "end")
        self._problem.insert("1.0", text)

    def _gather(self) -> dict:
        return {
            "purpose": self._purpose.get(),
            "target": self._get_target(),
            "product": self._product.get().strip(),
            "problem": self._problem.get("1.0", "end-1c").strip(),
            "message": self._message.get().strip(),
            "misconception": self._misconception.get().strip(),
            "hook_type": self._hook.get(),
            "length": self._length.get(),
        }

    def _generate(self):
        inputs = self._gather()
        if not inputs["product"]:
            self._status.configure(text="⚠ 상품/서비스를 입력해주세요", text_color="#f59e0b")
            return
        try:
            plan = cp.generate_full_plan(inputs)
            text = cp.format_plan(plan)
            self._last_text = text
            self._out.delete("1.0", "end")
            self._out.insert("1.0", text)
            self._status.configure(
                text=f"✅ 생성 완료 — 검수 {plan['review']['score']}점  ·  '복사'로 어디든 붙여넣으세요",
                text_color="#22c55e")
        except Exception as e:
            self._status.configure(text=f"❌ 생성 실패: {e}", text_color="#ef4444")

    def _copy(self):
        text = self._out.get("1.0", "end-1c")
        if not text.strip():
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self._status.configure(text="📋 복사됨! 메모장·블로그·영상편집기에 붙여넣으세요", text_color="#22c55e")

    def _save(self):
        text = self._out.get("1.0", "end-1c")
        if not text.strip():
            return
        from tkinter import filedialog
        out_dir = settings.get("output_dir") or str(Path.home())
        path = filedialog.asksaveasfilename(
            title="기획서 저장", initialdir=out_dir, defaultextension=".txt",
            initialfile="영상기획서.txt", filetypes=[("텍스트", "*.txt")])
        if path:
            try:
                Path(path).write_text(text, encoding="utf-8")
                self._status.configure(text=f"💾 저장됨: {Path(path).name}", text_color="#22c55e")
            except Exception as e:
                self._status.configure(text=f"❌ 저장 실패: {e}", text_color="#ef4444")
