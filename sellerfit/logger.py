"""
logger.py - SellerFit Slice 1 로깅 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
콘솔 + 파일 이중 로깅.
에러 발생 시 자동 파일 저장 (logs/ 폴더).
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

try:
    from config import LOG_DIR
except ImportError:
    LOG_DIR = Path(__file__).parent / "logs"
    LOG_DIR.mkdir(exist_ok=True)


class _ColorFormatter(logging.Formatter):
    """ANSI 컬러 포매터 (Windows 터미널에서도 동작)"""
    COLORS = {
        "DEBUG":    "\033[36m",  # cyan
        "INFO":     "\033[32m",  # green
        "WARNING":  "\033[33m",  # yellow
        "ERROR":    "\033[31m",  # red
        "CRITICAL": "\033[41m",  # red bg
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"{color}[{timestamp}] [{record.levelname:7}]{reset} {record.getMessage()}"


def _setup() -> logging.Logger:
    logger = logging.getLogger("sellerfit")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # 콘솔
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ColorFormatter())
    logger.addHandler(ch)

    # 파일 (일자별)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(LOG_DIR / f"{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    return logger


log = _setup()


# 편의 함수
def step(title: str):
    """단계 구분 로그"""
    log.info("")
    log.info("━" * 60)
    log.info(f"▶ {title}")
    log.info("━" * 60)


def success(msg: str):
    log.info(f"✅ {msg}")


def warn(msg: str):
    log.warning(f"⚠️  {msg}")


def fail(msg: str):
    log.error(f"❌ {msg}")
