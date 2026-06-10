"""
main.py - 영상 제작기 진입점 (기획 + 쇼츠)
"""

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
    sys.path.insert(0, str(BASE_DIR))
else:
    BASE_DIR = Path(__file__).parent


def main():
    # 크래시 로거 (있으면)
    try:
        from crash_logger import install_global_handler
        install_global_handler()
    except Exception:
        pass

    try:
        from ui_app import VideoMakerApp
        app = VideoMakerApp()
        app.mainloop()
    except Exception:
        import traceback
        try:
            from crash_logger import log_crash
            log_crash(context="영상 제작기 시작 오류")
        except Exception:
            pass
        msg = traceback.format_exc()
        try:
            import tkinter.messagebox as mb
            mb.showerror("영상 제작기 - 오류", msg)
        except Exception:
            print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
