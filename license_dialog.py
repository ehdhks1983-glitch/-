"""
license_dialog.py - 라이선스 / 체험판 다이얼로그
- 첫 실행: 체험판 시작 안내
- 체험 중: 남은 일수 표시 → 바로 앱 진입
- 만료: 잠금 화면 (키 입력만 가능)
- 날짜 조작: 차단 메시지
"""

import webbrowser
import customtkinter as ctk

from license_manager import (
    get_hwid, activate, check_license, LicenseStatus, APP_NAME,
)

# ─── 구매 링크 ───
PURCHASE_KAKAO = "https://open.kakao.com/o/sBWL4qpi"
PURCHASE_CAFE = "https://cafe.naver.com/mp3downs1"


class LicenseDialog(ctk.CTk):
    """라이선스 / 체험판 다이얼로그"""

    def __init__(self, license_info: dict):
        super().__init__()
        self.title(f"{APP_NAME} - 인증")
        self.geometry("540x520")
        self.resizable(False, False)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._activated: bool = False
        self._info = license_info
        self._hwid = license_info.get("hwid", get_hwid())

        self._build_ui()

        # 화면 중앙
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 540) // 2
        y = (self.winfo_screenheight() - 520) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        status = self._info.get("status")
        days_left = self._info.get("days_left", 0)
        message = self._info.get("message", "")

        # 헤더
        ctk.CTkLabel(
            self, text=f"🎞️ {APP_NAME}",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(24, 4))

        # ── 상태별 UI ──
        if status == LicenseStatus.TRIAL_ACTIVE:
            self._build_trial_ui(days_left, message)
        elif status == LicenseStatus.TRIAL_EXPIRED:
            self._build_expired_ui(message)
        elif status == LicenseStatus.DATE_TAMPERED:
            self._build_tampered_ui(message)
        else:
            self._build_expired_ui(message)

    def _build_trial_ui(self, days_left, message):
        """체험판 사용 중 → 남은 일수 표시 + 바로 사용 가능"""
        # 남은 일수
        color = "#22c55e" if days_left > 3 else "#f59e0b" if days_left > 1 else "#ef4444"
        ctk.CTkLabel(
            self, text=f"체험판: {days_left}일 남음",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=color,
        ).pack(pady=(8, 4))

        ctk.CTkLabel(
            self, text="체험 기간 동안 모든 기능을 무료로 사용할 수 있습니다.",
            font=ctk.CTkFont(size=12), text_color="gray60",
        ).pack(pady=(0, 16))

        # 바로 사용 버튼
        ctk.CTkButton(
            self, text="🚀 프로그램 시작", height=42, width=200,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._start_app,
        ).pack(pady=(0, 16))

        # 구분선
        ctk.CTkFrame(self, height=1, fg_color="gray30").pack(fill="x", padx=24, pady=8)

        # 라이선스 입력 (선택)
        ctk.CTkLabel(
            self, text="정식 라이선스가 있으신가요?",
            font=ctk.CTkFont(size=12), text_color="gray50",
        ).pack(pady=(8, 4))

        self._build_key_input()
        self._build_purchase_buttons()

    def _build_expired_ui(self, message):
        """만료 → 잠금 화면"""
        ctk.CTkLabel(
            self, text="⏰ 체험 기간이 만료되었습니다",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#ef4444",
        ).pack(pady=(8, 4))

        ctk.CTkLabel(
            self, text="계속 사용하려면 라이선스를 구매해주세요.",
            font=ctk.CTkFont(size=12), text_color="gray60",
        ).pack(pady=(0, 16))

        self._build_key_input()
        self._build_hwid_section()
        self._build_purchase_buttons()

        # 종료 버튼
        ctk.CTkButton(
            self, text="종료", height=36, width=100,
            font=ctk.CTkFont(size=13),
            fg_color="gray30", hover_color="gray20",
            command=self._on_exit,
        ).pack(pady=8)

    def _build_tampered_ui(self, message):
        """날짜 조작 감지 → 차단"""
        ctk.CTkLabel(
            self, text="⚠ 시스템 날짜 오류",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#ef4444",
        ).pack(pady=(8, 4))

        ctk.CTkLabel(
            self, text="시스템 날짜가 변경된 것으로 감지되었습니다.\n"
                       "날짜를 정상으로 복원한 후 다시 실행해주세요.\n\n"
                       "또는 정식 라이선스를 입력하세요.",
            font=ctk.CTkFont(size=12), text_color="gray60",
            justify="center",
        ).pack(pady=(0, 16))

        self._build_key_input()
        self._build_hwid_section()

        ctk.CTkButton(
            self, text="종료", height=36, width=100,
            fg_color="gray30", hover_color="gray20",
            command=self._on_exit,
        ).pack(pady=8)

    def _build_key_input(self):
        """라이선스 키 입력 섹션"""
        key_frame = ctk.CTkFrame(self, fg_color="gray15", corner_radius=10)
        key_frame.pack(padx=24, pady=(0, 8), fill="x")

        ctk.CTkLabel(
            key_frame, text="🔑 라이선스 키",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 4))

        input_row = ctk.CTkFrame(key_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=16, pady=(0, 12))

        self._key_entry = ctk.CTkEntry(
            input_row, font=ctk.CTkFont(size=13, family="Consolas"),
            height=36, placeholder_text="XXXX-XXXX-XXXX-XXXX",
        )
        self._key_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._key_entry.bind("<Return>", lambda e: self._try_activate())

        ctk.CTkButton(
            input_row, text="✅ 인증", width=70, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._try_activate,
        ).pack(side="right")

        self._status_label = ctk.CTkLabel(
            key_frame, text="", font=ctk.CTkFont(size=11),
        )
        self._status_label.pack(pady=(0, 8))

    def _build_hwid_section(self):
        """HWID 표시 + 복사"""
        hwid_frame = ctk.CTkFrame(self, fg_color="gray15", corner_radius=10)
        hwid_frame.pack(padx=24, pady=(0, 8), fill="x")

        ctk.CTkLabel(
            hwid_frame, text="📋 내 PC 고유 ID (HWID)",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(8, 2))

        row = ctk.CTkFrame(hwid_frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))

        hwid_entry = ctk.CTkEntry(
            row, font=ctk.CTkFont(size=12, family="Consolas"), height=28,
        )
        hwid_entry.insert(0, self._hwid)
        hwid_entry.configure(state="readonly")
        hwid_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            row, text="📋 복사", width=60, height=28,
            font=ctk.CTkFont(size=11),
            command=self._copy_hwid,
        ).pack(side="right")

    def _build_purchase_buttons(self):
        """구매 링크 버튼"""
        buy_frame = ctk.CTkFrame(self, fg_color="transparent")
        buy_frame.pack(pady=(4, 8))

        ctk.CTkButton(
            buy_frame, text="💬 카카오톡 문의", height=32, width=140,
            font=ctk.CTkFont(size=12),
            fg_color="#FEE500", hover_color="#E5CC00", text_color="black",
            command=lambda: webbrowser.open(PURCHASE_KAKAO),
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            buy_frame, text="🌐 네이버 카페", height=32, width=140,
            font=ctk.CTkFont(size=12),
            fg_color="#03C75A", hover_color="#02A94D",
            command=lambda: webbrowser.open(PURCHASE_CAFE),
        ).pack(side="left", padx=4)

    def _copy_hwid(self):
        self.clipboard_clear()
        self.clipboard_append(self._hwid)
        self.update()
        if hasattr(self, '_status_label'):
            self._status_label.configure(
                text="✅ HWID 복사됨", text_color="#22c55e")

    def _try_activate(self):
        key = self._key_entry.get().strip().upper()
        if not key:
            self._status_label.configure(
                text="⚠ 키를 입력해주세요", text_color="#f59e0b")
            return

        result = activate(key)
        if result["success"]:
            self._status_label.configure(
                text=result["message"], text_color="#22c55e")
            self._activated = True
            self.after(800, self.destroy)
        else:
            self._status_label.configure(
                text=result["message"], text_color="#ef4444")

    def _start_app(self):
        """체험판 → 바로 앱 시작"""
        self._activated = True
        self.destroy()

    def _on_exit(self):
        self._activated = False
        self.destroy()

    @property
    def activated(self) -> bool:
        return self._activated

    def protocol(self, name, func=None):
        """WM_DELETE_WINDOW 처리"""
        if name == "WM_DELETE_WINDOW":
            super().protocol(name, self._on_exit)
        else:
            super().protocol(name, func)
