"""
gui_app.py - SellerFit Slice 1 GUI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CustomTkinter 다크모드.

흐름:
  1. 시작 시 환경 점검 (API 키 + 반품지/출고지)
  2. 상품번호 입력 → [조회] → 상품정보·가격·카테고리·이미지 표시
  3. 가격 모드/수치 조정 가능 → [다시 계산]
  4. [쿠팡에 등록] → 실제 등록

모든 작업은 별도 스레드 (UI 안 멈춤).
UI 업데이트는 after()로 메인 스레드에서 안전하게.
"""

import threading
import queue
from datetime import datetime

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter 미설치. pip install customtkinter")

from pipeline_service import SellerFitService, PreparedProduct
from config import pricing_cfg


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# 가격 모드 표시명
PRICING_MODES = [
    ("multiply", "배수 (도매가 × N)"),
    ("add_margin", "마진율 (+N%)"),
    ("min_margin", "최소마진 (N% 보장)"),
]


class SellerFitGUI(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("SellerFit — 도매꾹 → 쿠팡 자동등록 (Slice 1)")
        self.geometry("760x820")
        self.minsize(720, 760)

        self.service = SellerFitService()
        self.prepared: PreparedProduct = None
        self._log_queue = queue.Queue()
        self._busy = False

        self._build_ui()
        self._poll_log_queue()

        # 시작 시 환경 점검 (백그라운드)
        self.after(300, self._check_env_async)

    # ═══════════════════════════════════════════════════════════
    # UI 구성
    # ═══════════════════════════════════════════════════════════
    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}

        # ── 헤더 ──
        header = ctk.CTkLabel(
            self, text="🛒 SellerFit — 도매꾹 → 쿠팡 자동등록",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        header.pack(pady=(16, 4))

        self.env_label = ctk.CTkLabel(
            self, text="환경 점검 중...",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.env_label.pack(pady=(0, 8))

        # ── 입력 영역 ──
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(fill="x", **pad)

        ctk.CTkLabel(input_frame, text="도매꾹 상품번호",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 2))

        row = ctk.CTkFrame(input_frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))

        self.item_entry = ctk.CTkEntry(
            row, placeholder_text="예: 23828709", height=40,
            font=ctk.CTkFont(size=14),
        )
        self.item_entry.pack(side="left", fill="x", expand=True)
        self.item_entry.bind("<Return>", lambda e: self._fetch_async())

        self.fetch_btn = ctk.CTkButton(
            row, text="조회하기", width=110, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._fetch_async,
        )
        self.fetch_btn.pack(side="left", padx=(8, 0))

        # ── 가격 설정 영역 ──
        price_frame = ctk.CTkFrame(self)
        price_frame.pack(fill="x", **pad)

        ctk.CTkLabel(price_frame, text="💰 가격 설정",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 2))

        price_row = ctk.CTkFrame(price_frame, fg_color="transparent")
        price_row.pack(fill="x", padx=12, pady=(0, 12))

        self.mode_var = ctk.StringVar(value=PRICING_MODES[0][1])
        self.mode_menu = ctk.CTkOptionMenu(
            price_row, values=[m[1] for m in PRICING_MODES],
            variable=self.mode_var, width=200, height=36,
            command=lambda _: self._recalc_if_ready(),
        )
        self.mode_menu.pack(side="left")

        self.value_entry = ctk.CTkEntry(
            price_row, width=90, height=36, placeholder_text="2.5",
        )
        self.value_entry.insert(0, str(pricing_cfg.multiplier))
        self.value_entry.pack(side="left", padx=(8, 0))

        self.recalc_btn = ctk.CTkButton(
            price_row, text="다시 계산", width=100, height=36,
            command=self._recalc_if_ready, state="disabled",
        )
        self.recalc_btn.pack(side="left", padx=(8, 0))

        # ── 상품 정보 표시 ──
        self.info_frame = ctk.CTkFrame(self)
        self.info_frame.pack(fill="x", **pad)

        ctk.CTkLabel(self.info_frame, text="📦 상품 정보",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        self.info_text = ctk.CTkLabel(
            self.info_frame, text="(조회하면 여기에 표시됩니다)",
            font=ctk.CTkFont(size=13), justify="left", anchor="w",
        )
        self.info_text.pack(fill="x", padx=12, pady=(0, 12))

        # ── 등록 버튼 ──
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", **pad)

        self.approval_var = ctk.BooleanVar(value=False)
        self.approval_check = ctk.CTkCheckBox(
            action_row, text="등록 후 즉시 승인요청 (체크 안 하면 임시저장)",
            variable=self.approval_var, font=ctk.CTkFont(size=12),
        )
        self.approval_check.pack(anchor="w", pady=(0, 8))

        self.register_btn = ctk.CTkButton(
            action_row, text="🚀 쿠팡에 등록하기", height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2d7d46", hover_color="#236337",
            command=self._register_async, state="disabled",
        )
        self.register_btn.pack(fill="x")

        # ── 로그 ──
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, **pad)

        ctk.CTkLabel(log_frame, text="📋 실시간 로그",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        self.log_box = ctk.CTkTextbox(
            log_frame, font=ctk.CTkFont(size=12, family="Consolas"),
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_box.configure(state="disabled")

    # ═══════════════════════════════════════════════════════════
    # 로그 시스템 (스레드 → UI 안전 전달)
    # ═══════════════════════════════════════════════════════════
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put(f"[{ts}] {msg}")

    def _poll_log_queue(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    # ═══════════════════════════════════════════════════════════
    # 환경 점검
    # ═══════════════════════════════════════════════════════════
    def _check_env_async(self):
        def task():
            self._log("환경 점검 중...")
            env = self.service.check_environment()
            self.after(0, lambda: self._on_env_checked(env))
        threading.Thread(target=task, daemon=True).start()

    def _on_env_checked(self, env: dict):
        for m in env["messages"]:
            self._log(m)
        if env["ok"]:
            self.env_label.configure(text=env["messages"][-1], text_color="#4ade80")
        else:
            self.env_label.configure(
                text="⚠️ 설정 필요 — 로그 확인 (.env 점검)",
                text_color="#f87171",
            )

    # ═══════════════════════════════════════════════════════════
    # 가격 모드 헬퍼
    # ═══════════════════════════════════════════════════════════
    def _current_mode_key(self) -> str:
        label = self.mode_var.get()
        for key, lbl in PRICING_MODES:
            if lbl == label:
                return key
        return "multiply"

    def _current_value(self) -> float:
        try:
            return float(self.value_entry.get().strip())
        except ValueError:
            return pricing_cfg.multiplier

    # ═══════════════════════════════════════════════════════════
    # 조회
    # ═══════════════════════════════════════════════════════════
    def _fetch_async(self):
        if self._busy:
            return
        item_no = self.item_entry.get().strip()
        if not item_no:
            self._log("⚠️ 상품번호를 입력하세요")
            return

        self._set_busy(True)
        self.prepared = None
        self.register_btn.configure(state="disabled")
        self.info_text.configure(text="조회 중...")

        mode = self._current_mode_key()
        value = self._current_value()

        def task():
            prepared = self.service.fetch_product(
                item_no, pricing_mode=mode, pricing_value=value,
                progress=self._log,
            )
            self.after(0, lambda: self._on_fetched(prepared))

        threading.Thread(target=task, daemon=True).start()

    def _on_fetched(self, prepared: PreparedProduct):
        self.prepared = prepared
        self._set_busy(False)

        if not prepared.ok:
            self.info_text.configure(
                text=f"❌ 조회 실패\n{prepared.error}", text_color="#f87171")
            self.register_btn.configure(state="disabled")
            self.recalc_btn.configure(state="disabled")
            return

        p = prepared
        margin_color = "#4ade80" if p.margin_rate >= 30 else "#fbbf24"
        info = (
            f"상품명:    {p.title[:45]}\n"
            f"도매가:    {p.base_price:,}원\n"
            f"판매가:    {p.sale_price:,}원  (마진 {p.margin_rate:.1f}%)\n"
            f"카테고리:  {p.category_name}  ({p.category_code})\n"
            f"이미지:    {len(p.usable_image_urls)}장 사용 가능 / 원본 {p.image_count}장\n"
            f"옵션:      {p.option_count}개 (Slice1은 단일상품으로 등록)"
        )
        self.info_text.configure(text=info, text_color="white")
        self.register_btn.configure(state="normal")
        self.recalc_btn.configure(state="normal")

    # ═══════════════════════════════════════════════════════════
    # 다시 계산 (조회 데이터 재활용, 가격만 갱신)
    # ═══════════════════════════════════════════════════════════
    def _recalc_if_ready(self):
        # 조회 안 됐으면 무시
        if not self.prepared or not self.prepared.ok:
            return
        # 가격만 다시 → 간단히 재조회 (도매꾹 캐시 안 해서 재호출되지만 Slice1 허용)
        self._log("가격 재계산 위해 다시 조회...")
        self._fetch_async()

    # ═══════════════════════════════════════════════════════════
    # 등록
    # ═══════════════════════════════════════════════════════════
    def _register_async(self):
        if self._busy or not self.prepared or not self.prepared.ok:
            return

        self._set_busy(True)
        approval = self.approval_var.get()

        def task():
            result = self.service.register_product(
                self.prepared, request_approval=approval, progress=self._log,
            )
            self.after(0, lambda: self._on_registered(result))

        threading.Thread(target=task, daemon=True).start()

    def _on_registered(self, result: dict):
        self._set_busy(False)
        if result["ok"]:
            self._log(f"🎉 완료! 쿠팡 상품ID: {result['seller_product_id']}")
            self.info_text.configure(
                text=self.info_text.cget("text") +
                f"\n\n✅ 등록 성공! 상품ID: {result['seller_product_id']}",
                text_color="#4ade80",
            )
            # 중복 등록 방지
            self.register_btn.configure(state="disabled")
        else:
            self._log(f"❌ 등록 실패: {result['error']}")

    # ═══════════════════════════════════════════════════════════
    # busy 상태
    # ═══════════════════════════════════════════════════════════
    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.fetch_btn.configure(state=state)
        if busy:
            self.fetch_btn.configure(text="처리 중...")
        else:
            self.fetch_btn.configure(text="조회하기")


def main():
    app = SellerFitGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
