"""
tts_dialog.py - 나래이션 음성(ElevenLabs) 설정 창
자연스러운 AI 음성을 쓰려면 ElevenLabs API 키와 Voice ID를 넣는다.
키가 없으면 윈도우 기본 음성으로 자동 동작(품질은 낮음).
"""

import os
import sys
import threading
from pathlib import Path

import customtkinter as ctk

from config import settings
from tts_engine import (tts_settings, test_elevenlabs, test_edge,
                        KOREAN_EDGE_VOICES, EDGE_VOICE_NAMES, EDGE_VOICE_IDS)


class TTSDialog(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("🎙 나래이션 음성 설정")
        self.geometry("520x560")
        self.resizable(False, False)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 520) // 2
        y = (self.winfo_screenheight() - 560) // 2
        self.geometry(f"+{x}+{y}")
        self.transient(master)
        self.grab_set()
        self._build()

    def _build(self):
        f = ctk.CTkScrollableFrame(self, fg_color="gray12")
        f.pack(fill="both", expand=True, padx=12, pady=12)
        pad = {"padx": 14, "pady": (6, 2), "anchor": "w", "fill": "x"}

        ctk.CTkLabel(f, text="나래이션 음성 설정",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(**pad)
        ctk.CTkLabel(
            f, text="윈도우 기본 음성은 로봇 같아 유튜브엔 약합니다.\n"
                    "Edge(무료)는 사람 같은 한국어 음성을 공짜로 줍니다(인터넷 필요).\n"
                    "ElevenLabs(월 $5~)는 가장 자연스럽지만 API 키가 필요해요.",
            font=ctk.CTkFont(size=11), text_color="gray60", justify="left").pack(**pad)

        # ── 음성 엔진 선택 (1-2) ──
        ctk.CTkLabel(f, text="음성 엔진", font=ctk.CTkFont(size=13, weight="bold")).pack(**pad)
        self._engine_map = {"자동 (추천)": "auto", "Edge (무료)": "edge",
                            "ElevenLabs": "elevenlabs", "시스템 음성": "system"}
        self._engine_rev = {v: k for k, v in self._engine_map.items()}
        self._engine_var = ctk.StringVar(
            value=self._engine_rev.get(tts_settings.get("engine"), "자동 (추천)"))
        ctk.CTkOptionMenu(f, values=list(self._engine_map.keys()),
                          variable=self._engine_var).pack(**pad)

        # ── Edge 한국어 보이스 (무료) ──
        ctk.CTkLabel(f, text="Edge 한국어 보이스 (무료)",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(**pad)
        self._edge_names = [n for n, _ in KOREAN_EDGE_VOICES]
        self._edge_var = ctk.StringVar(
            value=EDGE_VOICE_IDS.get(tts_settings.get("edge_voice"), self._edge_names[0]))
        ctk.CTkOptionMenu(f, values=self._edge_names, variable=self._edge_var).pack(**pad)
        ctk.CTkButton(f, text="🔊 Edge 음성 테스트", height=30,
                      font=ctk.CTkFont(size=12), fg_color="#16a34a", hover_color="#15803d",
                      command=self._test_edge).pack(**pad)

        ctk.CTkLabel(f, text="── ElevenLabs (선택, 유료) ──",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(**pad)
        self._use = ctk.BooleanVar(value=tts_settings.get("use_elevenlabs"))
        ctk.CTkSwitch(f, text="ElevenLabs 자연스러운 음성 사용", variable=self._use,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(**pad)

        ctk.CTkLabel(f, text="API 키", font=ctk.CTkFont(size=12, weight="bold")).pack(**pad)
        self._key = ctk.CTkEntry(f, font=ctk.CTkFont(size=12), height=32, show="•",
                                 placeholder_text="ElevenLabs > Profile > API Key")
        self._key.insert(0, tts_settings.get("api_key") or "")
        self._key.pack(**pad)

        ctk.CTkLabel(f, text="Voice ID", font=ctk.CTkFont(size=12, weight="bold")).pack(**pad)
        self._voice = ctk.CTkEntry(f, font=ctk.CTkFont(size=12), height=32,
                                   placeholder_text="ElevenLabs > Voices > (음성) > Voice ID 복사")
        self._voice.insert(0, tts_settings.get("voice_id") or "")
        self._voice.pack(**pad)

        self._stab = self._slider(f, "안정성", tts_settings.get("stability"))
        self._sim = self._slider(f, "유사도", tts_settings.get("similarity"))

        ctk.CTkLabel(f, text="💡 Voice ID는 ElevenLabs 사이트의 음성 페이지에서 복사합니다.",
                     font=ctk.CTkFont(size=10), text_color="gray55", justify="left").pack(**pad)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(btns, text="🔊 음성 테스트", height=38, font=ctk.CTkFont(size=13),
                      fg_color="#0ea5e9", hover_color="#0284c7",
                      command=self._test).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(btns, text="💾 저장", height=38, font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color="#2563eb", hover_color="#1d4ed8",
                      command=self._save).pack(side="left", expand=True, fill="x", padx=(4, 0))
        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray60")
        self._status.pack(padx=12, pady=(0, 8), anchor="w")

    def _slider(self, parent, label, val):
        fr = ctk.CTkFrame(parent, fg_color="transparent")
        fr.pack(fill="x", padx=14, pady=(6, 0))
        ctk.CTkLabel(fr, text=label, font=ctk.CTkFont(size=12), width=60, anchor="w").pack(side="left")
        var = ctk.IntVar(value=int(val))
        lbl = ctk.CTkLabel(fr, text=f"{int(val)}%", font=ctk.CTkFont(size=12), width=45)
        ctk.CTkSlider(fr, from_=0, to=100, variable=var, width=150,
                      command=lambda _=None, l=lbl, v=var: l.configure(text=f"{v.get()}%")).pack(side="left", padx=6)
        lbl.pack(side="left")
        return var

    def _sync(self):
        tts_settings.set("engine", self._engine_map.get(self._engine_var.get(), "auto"))
        tts_settings.set("edge_voice",
                         EDGE_VOICE_NAMES.get(self._edge_var.get(), "ko-KR-SunHiNeural"))
        tts_settings.set("use_elevenlabs", self._use.get())
        tts_settings.set("api_key", self._key.get().strip())
        tts_settings.set("voice_id", self._voice.get().strip())
        tts_settings.set("stability", self._stab.get())
        tts_settings.set("similarity", self._sim.get())

    def _save(self):
        self._sync()
        tts_settings.save()
        self._status.configure(text="💾 저장됐어요. 이제 쇼츠 나래이션이 이 음성으로 만들어집니다.",
                               text_color="#22c55e")

    def _test(self):
        key = self._key.get().strip()
        voice = self._voice.get().strip()
        if not key or not voice:
            self._status.configure(text="⚠ API 키와 Voice ID를 먼저 입력하세요", text_color="#f59e0b")
            return
        self._status.configure(text="🔊 음성 생성 중... (인터넷 필요, 몇 초)", text_color="white")
        threading.Thread(target=self._run_test, args=(key, voice), daemon=True).start()

    def _run_test(self, key, voice):
        out_dir = settings.get("output_dir") or str(Path.home())
        out = os.path.join(out_dir, "voice_test.mp3")
        r = test_elevenlabs(key, voice, out, model=tts_settings.get("model"))
        def done():
            if r and Path(r).exists():
                self._status.configure(text=f"✅ 성공! 들어보세요: {Path(r).name}", text_color="#22c55e")
                try:
                    if sys.platform == "win32":
                        os.startfile(r)
                except Exception:
                    pass
            else:
                self._status.configure(
                    text="❌ 실패 — API 키/Voice ID 또는 인터넷 연결을 확인하세요", text_color="#ef4444")
        self.after(0, done)

    def _test_edge(self):
        self._status.configure(text="🔊 Edge 음성 생성 중... (무료, 인터넷 필요, 몇 초)",
                               text_color="white")
        voice = EDGE_VOICE_NAMES.get(self._edge_var.get(), "ko-KR-SunHiNeural")
        threading.Thread(target=self._run_edge_test, args=(voice,), daemon=True).start()

    def _run_edge_test(self, voice):
        out_dir = settings.get("output_dir") or str(Path.home())
        out = os.path.join(out_dir, "voice_test_edge.mp3")
        r = test_edge(voice, out)
        def done():
            if r and Path(r).exists():
                self._status.configure(text=f"✅ 성공! 들어보세요: {Path(r).name}", text_color="#22c55e")
                try:
                    if sys.platform == "win32":
                        os.startfile(r)
                except Exception:
                    pass
            else:
                self._status.configure(
                    text="❌ Edge 실패 — 인터넷 연결을 확인하세요(edge-tts 설치 필요)",
                    text_color="#ef4444")
        self.after(0, done)
