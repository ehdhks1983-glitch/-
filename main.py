"""
main.py - GIF Maker Pro 진입점
1) 크래시 로거 설치 → 2) 라이선스 체크 → 3) 메인 앱 실행
"""

import os
import sys
from pathlib import Path

# ─── EXE 빌드 시 경로 보정 ───
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
    sys.path.insert(0, str(BASE_DIR))
else:
    BASE_DIR = Path(__file__).parent


def is_dev_mode() -> bool:
    """개발 모드 감지. 배포(frozen)에선 무조건 False."""
    if getattr(sys, 'frozen', False):
        return False
    if os.environ.get("GMP_DEV") == "1":
        return True
    if (BASE_DIR / ".dev_mode").exists():
        return True
    return False


def main():
    # ── 1. 크래시 로거 설치 (최우선) ──
    try:
        from crash_logger import install_global_handler
        install_global_handler()
    except Exception:
        pass  # 로거 실패해도 앱은 계속 실행

    try:
        # ── 2. 라이선스 / 체험판 검증 ──
        if is_dev_mode():
            print("🔧 [DEV MODE] 라이선스 검증 건너뜀")
        else:
            from license_manager import check_license, LicenseStatus

            info = check_license()
            status = info["status"]

            if status == LicenseStatus.ACTIVATED:
                # 정식 라이선스 → 바로 실행
                pass
            elif status == LicenseStatus.TRIAL_ACTIVE:
                # 체험판 → 남은 일수 표시 후 진행
                from license_dialog import LicenseDialog
                dialog = LicenseDialog(info)
                dialog.mainloop()
                if not dialog.activated:
                    sys.exit(0)
            else:
                # 만료 / 날짜 조작 → 잠금 화면
                from license_dialog import LicenseDialog
                dialog = LicenseDialog(info)
                dialog.mainloop()
                if not dialog.activated:
                    sys.exit(0)

        # ── 3. 메인 앱 실행 ──
        from ui_app import GifMakerApp
        app = GifMakerApp()
        app.mainloop()

    except Exception as e:
        # 명시적 에러 로깅 (excepthook가 처리 안 하는 경우 대비)
        try:
            from crash_logger import log_crash
            log_path = log_crash(context="앱 시작 시 오류")
        except Exception:
            log_path = None

        import traceback
        msg = f"앱 시작 오류:\n{traceback.format_exc()}"
        if log_path:
            msg += f"\n\n로그: {log_path}"

        try:
            import tkinter.messagebox as mb
            mb.showerror("GIF Maker Pro - 오류", msg)
        except Exception:
            print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
