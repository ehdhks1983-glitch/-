"""
about_dialog.py - 정보/도움말 다이얼로그
앱 사용법, 라이선스 정보, 문의 채널, 로그 폴더 등 안내
"""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path

import customtkinter as ctk

from config import APP_NAME, APP_VERSION
from license_manager import get_hwid, is_activated, load_saved_license
from crash_logger import get_log_dir


# ─── 연락처 / 링크 (도완님 정보로 수정) ───
CONTACT_KAKAO = "https://open.kakao.com/o/sBWL4qpi"
CONTACT_EMAIL = "support@example.com"  # TODO: 실제 이메일로 교체
CONTACT_CAFE = "https://cafe.naver.com/mp3downs1"


class AboutDialog(ctk.CTkToplevel):
    """정보/도움말 창"""

    def __init__(self, master=None):
        super().__init__(master)
        self.title(f"{APP_NAME} - 정보")
        self.geometry("560x640")
        self.resizable(False, False)

        # 중앙 배치
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 560) // 2
        y = (self.winfo_screenheight() - 640) // 2
        self.geometry(f"+{x}+{y}")

        self.transient(master)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        # ── 헤더 ──
        header = ctk.CTkFrame(self, fg_color="gray10", corner_radius=0, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text=f"🎞️ {APP_NAME}",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(16, 2))

        ctk.CTkLabel(
            header, text=f"버전 {APP_VERSION}",
            font=ctk.CTkFont(size=12), text_color="gray60",
        ).pack()

        # ── 탭 뷰 ──
        tabview = ctk.CTkTabview(
            self, fg_color="gray12",
            segmented_button_selected_color="#2563eb",
        )
        tabview.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        # 탭들
        tab_about = tabview.add("📋 사용법")
        tab_license = tabview.add("🔑 라이선스")
        tab_contact = tabview.add("📧 문의")
        tab_logs = tabview.add("📁 로그")

        self._build_about_tab(tab_about)
        self._build_license_tab(tab_license)
        self._build_contact_tab(tab_contact)
        self._build_logs_tab(tab_logs)

        # ── 닫기 버튼 ──
        ctk.CTkButton(
            self, text="닫기", height=36, width=120,
            font=ctk.CTkFont(size=13),
            command=self.destroy,
        ).pack(pady=(0, 12))

    def _build_about_tab(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        sections = [
            ("🖼️ 이미지 합치기",
             "여러 이미지를 합쳐 GIF/WebP/APNG 움짤 만들기\n"
             "• 이미지 추가 → 순서 조정 → 변환\n"
             "• 프레임당 시간 개별 설정 가능\n"
             "• 드래그앤드롭 지원"),

            ("🎬 영상 → 움짤",
             "영상 파일을 움짤로 변환\n"
             "• 시작/끝 시간 자유 조정\n"
             "• 미리보기로 구간 확인\n"
             "• 자막 추가 가능 (여러 개)\n"
             "• 안전 모드: PC 메모리에 맞춰 자동 설정"),

            ("🔴 화면 녹화",
             "컴퓨터 화면을 녹화해서 바로 움짤로 변환\n"
             "• 전체화면 또는 영역 선택\n"
             "• FPS / 해상도 / 최대 녹화 시간 설정\n"
             "• 일시정지 / 재개 지원"),

            ("✏️ 편집",
             "기존 움짤 파일 열어서 편집\n"
             "• 크롭, 리사이즈, 회전, 반전\n"
             "• 속도 조절, 역재생, 부메랑\n"
             "• 흑백 / 세피아 필터\n"
             "• 포맷 변환 (GIF ↔ WebP ↔ APNG)"),

            ("💡 팁",
             "• 안전 모드는 항상 켜두세요 (PC 안 멈춤)\n"
             "• 자막은 미리보기에서 먼저 확인하세요\n"
             "• 30초 이상은 용량이 매우 큽니다\n"
             "• GIF는 256색 제한, 선명도 필요 시 WebP 추천"),
        ]

        for title, content in sections:
            section = ctk.CTkFrame(frame, fg_color="gray18", corner_radius=8)
            section.pack(fill="x", pady=4)

            ctk.CTkLabel(
                section, text=title,
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 4))

            ctk.CTkLabel(
                section, text=content,
                font=ctk.CTkFont(size=12),
                text_color="gray80",
                justify="left", anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 10))

    def _build_license_tab(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        activated = is_activated()

        # 상태
        status_color = "#22c55e" if activated else "#ef4444"
        status_text = "✅ 정상 활성화됨" if activated else "❌ 미활성화"

        ctk.CTkLabel(
            frame, text="라이선스 상태",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            frame, text=status_text,
            font=ctk.CTkFont(size=14), text_color=status_color,
        ).pack(anchor="w", pady=(0, 16))

        # HWID
        ctk.CTkLabel(
            frame, text="내 PC HWID",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        hwid_frame = ctk.CTkFrame(frame, fg_color="transparent")
        hwid_frame.pack(fill="x", pady=(0, 4))

        hwid_entry = ctk.CTkEntry(
            hwid_frame, font=ctk.CTkFont(size=13, family="Consolas"),
            height=32,
        )
        hwid_entry.insert(0, get_hwid())
        hwid_entry.configure(state="readonly")
        hwid_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def copy_hwid():
            self.clipboard_clear()
            self.clipboard_append(get_hwid())
            self.update()

        ctk.CTkButton(
            hwid_frame, text="📋 복사", width=60, height=32,
            font=ctk.CTkFont(size=12),
            command=copy_hwid,
        ).pack(side="right")

        # 라이선스 키 (있으면 표시)
        key = load_saved_license()
        if key:
            ctk.CTkLabel(
                frame, text="라이선스 키",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(anchor="w", pady=(16, 4))

            key_entry = ctk.CTkEntry(
                frame, font=ctk.CTkFont(size=13, family="Consolas"),
                height=32,
            )
            key_entry.insert(0, key)
            key_entry.configure(state="readonly")
            key_entry.pack(fill="x")

        # 안내
        ctk.CTkLabel(
            frame,
            text="\n💡 라이선스 문의는 '문의' 탭을 참조하세요.",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w", justify="left",
        ).pack(fill="x", pady=(16, 0))

    def _build_contact_tab(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame, text="문의 / 기술 지원",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 12))

        # 카카오톡
        kakao_frame = ctk.CTkFrame(frame, fg_color="gray18", corner_radius=8)
        kakao_frame.pack(fill="x", pady=4)

        ctk.CTkLabel(
            kakao_frame, text="💬 카카오톡 오픈채팅",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            kakao_frame, text=CONTACT_KAKAO,
            font=ctk.CTkFont(size=11), text_color="gray60",
            anchor="w",
        ).pack(fill="x", padx=12)

        ctk.CTkButton(
            kakao_frame, text="🔗 오픈채팅 열기", height=28,
            font=ctk.CTkFont(size=12),
            command=lambda: webbrowser.open(CONTACT_KAKAO),
        ).pack(padx=12, pady=(4, 10), anchor="w")

        # 네이버 카페
        cafe_frame = ctk.CTkFrame(frame, fg_color="gray18", corner_radius=8)
        cafe_frame.pack(fill="x", pady=4)

        ctk.CTkLabel(
            cafe_frame, text="🌐 네이버 카페",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            cafe_frame, text=CONTACT_CAFE,
            font=ctk.CTkFont(size=11), text_color="gray60",
            anchor="w",
        ).pack(fill="x", padx=12)

        ctk.CTkButton(
            cafe_frame, text="🔗 카페 열기", height=28,
            font=ctk.CTkFont(size=12),
            command=lambda: webbrowser.open(CONTACT_CAFE),
        ).pack(padx=12, pady=(4, 10), anchor="w")

        # 안내
        ctk.CTkLabel(
            frame,
            text="\n💡 문의 시 다음을 함께 보내주시면 도움이 됩니다:\n"
                 "  • '라이선스' 탭의 HWID\n"
                 "  • '로그' 탭의 최근 크래시 로그 (문제 발생 시)\n"
                 "  • 영상 파일 정보 (해상도, 길이)",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w", justify="left",
        ).pack(fill="x", pady=(8, 0))

    def _build_logs_tab(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame, text="로그 파일",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 8))

        log_dir = get_log_dir()

        # 로그 폴더 경로
        path_frame = ctk.CTkFrame(frame, fg_color="gray18", corner_radius=8)
        path_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            path_frame, text="📂 로그 폴더 위치",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))

        path_entry = ctk.CTkEntry(
            path_frame, font=ctk.CTkFont(size=11),
            height=28,
        )
        path_entry.insert(0, str(log_dir))
        path_entry.configure(state="readonly")
        path_entry.pack(fill="x", padx=12, pady=(0, 8))

        # 폴더 열기 + 복사 버튼
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkButton(
            btn_frame, text="📂 로그 폴더 열기", height=32,
            font=ctk.CTkFont(size=12),
            command=lambda: self._open_folder(log_dir),
        ).pack(side="left", padx=(0, 6))

        # 최근 로그 목록
        ctk.CTkLabel(
            frame, text="최근 크래시 로그 (최대 10개)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", pady=(8, 4))

        log_list = ctk.CTkScrollableFrame(frame, fg_color="gray18", height=180)
        log_list.pack(fill="both", expand=True)

        try:
            logs = sorted(
                log_dir.glob("crash_*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not logs:
                ctk.CTkLabel(
                    log_list, text="(크래시 로그 없음)",
                    font=ctk.CTkFont(size=11), text_color="gray50",
                ).pack(pady=20)
            else:
                for log in logs[:10]:
                    row = ctk.CTkFrame(log_list, fg_color="gray20", corner_radius=6)
                    row.pack(fill="x", pady=2, padx=4)

                    ctk.CTkLabel(
                        row, text=f"📄 {log.name}",
                        font=ctk.CTkFont(size=11),
                        anchor="w",
                    ).pack(side="left", fill="x", expand=True, padx=8, pady=6)

                    ctk.CTkButton(
                        row, text="열기", width=50, height=24,
                        font=ctk.CTkFont(size=10),
                        command=lambda p=log: self._open_file(p),
                    ).pack(side="right", padx=6, pady=6)
        except Exception:
            pass

    def _open_folder(self, path):
        """운영체제에 맞게 폴더 열기"""
        try:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def _open_file(self, path):
        """로그 파일을 기본 텍스트 에디터로 열기"""
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass
