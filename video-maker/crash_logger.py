"""
crash_logger.py - 크래시/에러 자동 로깅
- 예상치 못한 예외 발생 시 로그 파일 자동 저장
- 사용자가 도완님께 보낼 수 있도록 폴더 구조 정리
- 최근 10개 로그만 유지 (오래된 건 자동 삭제)
"""

import datetime
import os
import platform
import sys
import traceback
from pathlib import Path
from typing import Optional


# ─── 로그 저장 위치 ───
# 설정/로그/라이선스는 한 곳(config.DATA_DIR = AppData)에 모은다.
# crash_logger는 아주 이른 시점에 import되므로 config 로드 실패에도 견디게 폴백.
try:
    from config import DATA_DIR as _DATA_DIR, APP_NAME as _APP_NAME
    LOG_DIR = _DATA_DIR / "logs"
except Exception:
    _APP_NAME = "영상 제작기"  # config 로드 실패 시 표시용 폴백
    if getattr(sys, 'frozen', False):
        _BASE = Path(sys.executable).parent
    else:
        _BASE = Path(__file__).parent
    LOG_DIR = _BASE / "data" / "logs"

MAX_LOGS = 10  # 최근 N개만 유지


def _ensure_log_dir():
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _cleanup_old_logs():
    """MAX_LOGS 초과하는 오래된 로그 삭제"""
    try:
        logs = sorted(
            LOG_DIR.glob("crash_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in logs[MAX_LOGS:]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _system_info() -> str:
    """시스템 정보 수집"""
    try:
        info = {
            "App": _APP_NAME,
            "OS": f"{platform.system()} {platform.release()} ({platform.version()})",
            "Python": sys.version.split()[0],
            "Architecture": platform.machine(),
            "Frozen": getattr(sys, 'frozen', False),
            "Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())
    except Exception:
        return "  (시스템 정보 수집 실패)"


def log_crash(exc_info=None, context: str = "") -> Optional[str]:
    """
    크래시 로그 저장.

    Args:
        exc_info: sys.exc_info() 튜플 또는 None (자동 수집)
        context: 추가 컨텍스트 메시지

    Returns:
        저장된 로그 파일 경로 (실패 시 None)
    """
    _ensure_log_dir()

    if exc_info is None:
        exc_info = sys.exc_info()

    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOG_DIR / f"crash_{timestamp}.log"

        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write(f" {_APP_NAME} - 크래시 로그\n")
            f.write("=" * 70 + "\n\n")

            f.write("📋 시스템 정보\n")
            f.write(_system_info())
            f.write("\n\n")

            if context:
                f.write("📝 컨텍스트\n")
                f.write(f"  {context}\n\n")

            f.write("🔴 에러 정보\n")
            if exc_info and exc_info[0] is not None:
                tb_str = "".join(traceback.format_exception(*exc_info))
                f.write(tb_str)
            else:
                f.write("  (예외 정보 없음)\n")

            f.write("\n" + "=" * 70 + "\n")
            f.write(" 📧 이 파일을 판매자에게 전달해주세요\n")
            f.write("=" * 70 + "\n")

        _cleanup_old_logs()
        return str(log_file)
    except Exception:
        return None


def install_global_handler():
    """
    전역 예외 핸들러 설치.
    처리되지 않은 예외를 자동으로 로그에 기록.
    """
    default_handler = sys.excepthook

    def handler(exc_type, exc_value, exc_traceback):
        # KeyboardInterrupt는 무시
        if issubclass(exc_type, KeyboardInterrupt):
            default_handler(exc_type, exc_value, exc_traceback)
            return

        # 로그 저장
        log_path = log_crash((exc_type, exc_value, exc_traceback))

        # 사용자에게 알림
        try:
            import tkinter.messagebox as mb
            msg = "예기치 않은 오류가 발생했습니다.\n\n"
            if log_path:
                msg += f"로그 파일 저장됨:\n{log_path}\n\n"
                msg += "이 파일을 판매자에게 전달해주세요."
            else:
                msg += f"오류 내용:\n{exc_value}"
            mb.showerror(f"{_APP_NAME} - 오류", msg)
        except Exception:
            pass

        # 기본 핸들러도 호출 (콘솔 출력)
        default_handler(exc_type, exc_value, exc_traceback)

    sys.excepthook = handler


def get_log_dir() -> Path:
    """로그 폴더 경로 반환 (사용자가 열어볼 때)"""
    _ensure_log_dir()
    return LOG_DIR
