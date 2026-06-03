"""Logging configuration: dated UTF-8 files + optional UI forwarding.

Design notes
------------
* One named logger tree (``instaautobot``); ``get_logger`` returns children.
* A dated file handler writes ``logs/insta_YYYY-MM-DD.log`` in the app-data
  directory so a frozen EXE can always write logs.
* :class:`CallbackLogHandler` forwards formatted records to an arbitrary
  callback - the UI uses this to mirror logs into its on-screen panel without
  any direct coupling between core logic and CustomTkinter.
* :func:`install_excepthook` ensures *uncaught* exceptions (incl. in worker
  threads) are still written to the log instead of vanishing.
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys
import threading
from typing import Callable

import paths

ROOT_LOGGER_NAME = "instaautobot"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured = False
_lock = threading.Lock()


class CallbackLogHandler(logging.Handler):
    """A handler that pushes formatted log lines to a callback (e.g. the UI).

    The callback must be cheap and thread-safe-ish; the UI implementation
    enqueues the line and repaints from the main thread via ``after()``.
    """

    def __init__(self, callback: Callable[[str], None], level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._callback = callback
        self.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            self._callback(self.format(record))
        except Exception:  # never let logging crash the app
            self.handleError(record)


def _dated_log_path():
    today = _dt.date.today().isoformat()
    return paths.logs_dir() / f"insta_{today}.log"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure (once) and return the application's root logger."""
    global _configured
    with _lock:
        logger = logging.getLogger(ROOT_LOGGER_NAME)
        logger.setLevel(logging.DEBUG)
        if _configured:
            return logger

        paths.ensure_dirs()
        fmt = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

        file_handler = logging.FileHandler(_dated_log_path(), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler(stream=sys.stderr)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

        logger.propagate = False
        _configured = True
        return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the application's root logger."""
    if not name:
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def add_ui_handler(callback: Callable[[str], None], level: int = logging.INFO) -> CallbackLogHandler:
    """Attach a :class:`CallbackLogHandler` and return it (so it can be removed)."""
    handler = CallbackLogHandler(callback, level=level)
    logging.getLogger(ROOT_LOGGER_NAME).addHandler(handler)
    return handler


def remove_handler(handler: logging.Handler) -> None:
    logging.getLogger(ROOT_LOGGER_NAME).removeHandler(handler)


def install_excepthook(logger: logging.Logger | None = None) -> None:
    """Route uncaught exceptions (main + worker threads) into the log."""
    log = logger or get_logger()

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook

    # Python 3.8+: capture exceptions raised inside threads too.
    if hasattr(threading, "excepthook"):
        def _thread_hook(args):  # type: ignore[no-untyped-def]
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            log.critical(
                "Uncaught exception in thread %s",
                args.thread.name if args.thread else "?",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = _thread_hook  # type: ignore[assignment]
