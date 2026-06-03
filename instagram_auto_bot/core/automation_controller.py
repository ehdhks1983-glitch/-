"""Start / pause / stop state machine for background automation.

This is the piece that makes the UI feel responsive: every long-running job
runs on a worker thread and cooperates with a :class:`JobControl` handed to it.
The job calls ``control.checkpoint()`` / ``control.sleep()`` at safe points;
those calls block while paused and raise :class:`StopRequested` when the user
hits Stop, so work unwinds cleanly between steps (never mid-API-call).

Deliberately Tk-free so the whole concurrency model is unit-testable headless.
"""

from __future__ import annotations

import enum
import threading
import time
from typing import Any, Callable, Optional

from core.logging_setup import get_logger

log = get_logger("controller")


class StopRequested(Exception):
    """Raised inside a worker target when the user requested Stop."""


class WorkerState(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


class JobControl:
    """Cooperative pause/stop signal passed into a worker target.

    Worker code must periodically call :meth:`checkpoint` (or :meth:`sleep`,
    which checkpoints internally) so pause/stop can take effect.
    """

    def __init__(self, poll: float = 0.05) -> None:
        self._poll = poll
        self._pause = threading.Event()
        self._stop = threading.Event()

    # -- driven by the controller / UI ------------------------------------ #
    def request_pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def request_stop(self) -> None:
        self._stop.set()
        self._pause.clear()  # release any paused wait so it can observe stop

    # -- observable state ------------------------------------------------- #
    @property
    def paused(self) -> bool:
        return self._pause.is_set() and not self._stop.is_set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    # -- worker-facing ---------------------------------------------------- #
    def checkpoint(self) -> None:
        """Block while paused; raise :class:`StopRequested` if stopping."""
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(self._poll)
        if self._stop.is_set():
            raise StopRequested()

    def sleep(self, seconds: float) -> None:
        """Interruptible sleep. Honours pause (freezes countdown) and stop."""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            self.checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(self._poll, remaining))


class AutomationController:
    """Owns a single worker thread and its lifecycle.

    Parameters
    ----------
    on_state_change:
        Optional callback invoked (from the worker / caller thread) whenever the
        state changes. The UI wraps this with ``after()`` to update widgets on
        the main thread.
    """

    def __init__(self, on_state_change: Optional[Callable[[WorkerState], None]] = None) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._control: Optional[JobControl] = None
        self._state = WorkerState.IDLE
        self._on_state_change = on_state_change

    # -- state ------------------------------------------------------------ #
    @property
    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        return self.state in (WorkerState.RUNNING, WorkerState.PAUSED, WorkerState.STOPPING)

    def _set_state(self, new: WorkerState) -> None:
        with self._lock:
            if self._state == new:
                return
            self._state = new
        cb = self._on_state_change
        if cb is not None:
            try:
                cb(new)
            except Exception:  # never let a UI callback kill the worker
                log.exception("on_state_change callback failed")

    # -- lifecycle -------------------------------------------------------- #
    def start(
        self,
        target: Callable[..., Any],
        *args: Any,
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
        name: str = "insta-worker",
        **kwargs: Any,
    ) -> bool:
        """Run ``target(control, *args, **kwargs)`` on a worker thread.

        Returns False (and does nothing) if a job is already active.
        """
        with self._lock:
            if self.is_active:
                log.warning("start ignored - worker already %s", self._state.value)
                return False
            control = JobControl()
            self._control = control

        # Transition to RUNNING (and fire the callback) before launching the
        # thread, so the state is already RUNNING by the time start() returns.
        self._set_state(WorkerState.RUNNING)

        def _run() -> None:
            error: Optional[BaseException] = None
            result: Any = None
            try:
                result = target(control, *args, **kwargs)
            except StopRequested:
                log.info("worker stopped by user request")
            except Exception as exc:  # noqa: BLE001 - reported to UI + log
                error = exc
                log.exception("worker failed: %s", exc)
                if on_error is not None:
                    try:
                        on_error(exc)
                    except Exception:
                        log.exception("on_error callback failed")
            finally:
                with self._lock:
                    self._control = None
                self._set_state(WorkerState.IDLE)
                if error is None and on_done is not None:
                    try:
                        on_done(result)
                    except Exception:
                        log.exception("on_done callback failed")

        thread = threading.Thread(target=_run, name=name, daemon=True)
        with self._lock:
            self._thread = thread
        thread.start()
        return True

    def pause(self) -> None:
        with self._lock:
            if self._state == WorkerState.RUNNING and self._control is not None:
                self._control.request_pause()
                pause = True
            else:
                pause = False
        if pause:
            self._set_state(WorkerState.PAUSED)

    def resume(self) -> None:
        with self._lock:
            if self._state == WorkerState.PAUSED and self._control is not None:
                self._control.resume()
                resumed = True
            else:
                resumed = False
        if resumed:
            self._set_state(WorkerState.RUNNING)

    def stop(self, wait: bool = False, timeout: float = 5.0) -> None:
        with self._lock:
            ctrl = self._control
            thread = self._thread
            if ctrl is not None and self._state in (WorkerState.RUNNING, WorkerState.PAUSED):
                ctrl.request_stop()
                stopping = True
            else:
                stopping = False
        if stopping:
            self._set_state(WorkerState.STOPPING)
        if wait and thread is not None:
            thread.join(timeout)

    def join(self, timeout: Optional[float] = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
