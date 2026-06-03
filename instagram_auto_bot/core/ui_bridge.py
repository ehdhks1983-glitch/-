"""Thread-safe primitives bridging worker threads and the Tk main thread.

Tk widgets may only be touched from the main thread.  Workers therefore never
write to the UI directly; they push strings onto a :class:`LogQueue`, and the
UI drains it on a timer (``widget.after``).  Kept Tk-free and unit-testable.
"""

from __future__ import annotations

import queue
from typing import List


class LogQueue:
    """A bounded, never-blocking line buffer (many producers, one consumer).

    Producers (worker threads) call :meth:`push`; the UI thread calls
    :meth:`drain`.  When full, the oldest line is dropped so a producer is never
    blocked by a slow/paused UI.
    """

    def __init__(self, maxsize: int = 10_000) -> None:
        self._q: "queue.Queue[str]" = queue.Queue(maxsize=maxsize)

    def push(self, line: str) -> None:
        try:
            self._q.put_nowait(line)
        except queue.Full:
            try:
                self._q.get_nowait()      # drop oldest
                self._q.put_nowait(line)
            except queue.Empty:           # pragma: no cover - race only
                pass

    def drain(self, max_items: int = 500) -> List[str]:
        out: List[str] = []
        for _ in range(max_items):
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def __len__(self) -> int:
        return self._q.qsize()
