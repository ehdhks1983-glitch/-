"""Local scheduling queue with timing jitter (spec Stage 6).

Scheduled posts get a random +/- ``SCHEDULE_JITTER_MIN`` offset so publishing
never happens on a robotic exact-minute cadence (a ban-avoidance measure).  The
queue persists to the app-data dir so it survives restarts.  The tick loop runs
on the AutomationController, so global Pause/Stop apply.

Important: scheduled publishing only fires while the PC + program are running -
this is surfaced prominently in the UI.

clock / rng / sleep are injectable -> jitter, due-selection and the run loop are
all unit-testable offline.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

import config
import paths
from core.logging_setup import get_logger
from core.publish_flow import ImageSource

log = get_logger("scheduler")

_ISO = "%Y-%m-%dT%H:%M:%S"

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


def apply_jitter(when: datetime, jitter_min: int, rng: Optional[random.Random] = None) -> datetime:
    """Return ``when`` shifted by a uniform random offset in +/- jitter_min minutes."""
    rng = rng or random
    if jitter_min <= 0:
        return when
    delta = rng.uniform(-jitter_min, jitter_min)
    return when + timedelta(minutes=delta)


@dataclass
class ScheduledPost:
    id: str
    scheduled_at: datetime          # user-chosen time
    effective_at: datetime          # scheduled_at + jitter (actual fire time)
    topic: str
    media_type: str
    image_sources: List[ImageSource]
    status: str = STATUS_PENDING
    info: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scheduled_at": self.scheduled_at.strftime(_ISO),
            "effective_at": self.effective_at.strftime(_ISO),
            "topic": self.topic,
            "media_type": self.media_type,
            "image_sources": [asdict(s) for s in self.image_sources],
            "status": self.status,
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledPost":
        return cls(
            id=d["id"],
            scheduled_at=datetime.strptime(d["scheduled_at"], _ISO),
            effective_at=datetime.strptime(d["effective_at"], _ISO),
            topic=d["topic"],
            media_type=d["media_type"],
            image_sources=[ImageSource(**s) for s in d.get("image_sources", [])],
            status=d.get("status", STATUS_PENDING),
            info=d.get("info", ""),
        )


class Scheduler:
    def __init__(self, *, store_path: Optional[Path] = None, jitter_min: Optional[int] = None,
                 rng: Optional[random.Random] = None,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.path = store_path or (paths.appdata_dir() / "schedule.json")
        self.jitter_min = config.SCHEDULE_JITTER_MIN if jitter_min is None else jitter_min
        self.rng = rng or random.Random()
        self._clock = clock or datetime.now
        self._posts: List[ScheduledPost] = []
        self.load()

    # ---- persistence ---------------------------------------------------- #
    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self._posts = [ScheduledPost.from_dict(d) for d in raw]
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            self._posts = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump([p.to_dict() for p in self._posts], fh, ensure_ascii=False, indent=2)

    # ---- queue ops ------------------------------------------------------ #
    def add(self, scheduled_at: datetime, topic: str, media_type: str,
            image_sources: List[ImageSource]) -> ScheduledPost:
        post = ScheduledPost(
            id=uuid.uuid4().hex[:12],
            # second precision: schedule times don't need sub-second resolution
            # and this keeps the JSON round-trip lossless.
            scheduled_at=scheduled_at.replace(microsecond=0),
            effective_at=apply_jitter(scheduled_at, self.jitter_min, self.rng).replace(microsecond=0),
            topic=topic,
            media_type=media_type,
            image_sources=list(image_sources),
        )
        self._posts.append(post)
        self.save()
        log.info("예약 추가: '%s' %s (지터 적용 %s)", topic,
                 scheduled_at.strftime(_ISO), post.effective_at.strftime(_ISO))
        return post

    def remove(self, post_id: str) -> bool:
        before = len(self._posts)
        self._posts = [p for p in self._posts if p.id != post_id]
        if len(self._posts) != before:
            self.save()
            return True
        return False

    def all(self) -> List[ScheduledPost]:
        return list(sorted(self._posts, key=lambda p: p.effective_at))

    def pending(self) -> List[ScheduledPost]:
        return [p for p in self._posts if p.status == STATUS_PENDING]

    def due(self, now: Optional[datetime] = None) -> List[ScheduledPost]:
        now = now or self._clock()
        return [p for p in self.pending() if p.effective_at <= now]

    def mark(self, post: ScheduledPost, status: str, info: str = "") -> None:
        post.status = status
        post.info = info
        self.save()

    # ---- execution ------------------------------------------------------ #
    def run_due(self, runner: Callable[[ScheduledPost], object],
                now: Optional[datetime] = None, *, control=None) -> List[ScheduledPost]:
        """Run every due post via ``runner``; mark done/failed. Returns those run."""
        from core.automation_controller import StopRequested
        from core.instagram_api import AuthError

        ran: List[ScheduledPost] = []
        for post in self.due(now):
            if control is not None:
                control.checkpoint()
            try:
                log.info("예약 발행 실행: '%s'", post.topic)
                runner(post)
                self.mark(post, STATUS_DONE)
                ran.append(post)
            except StopRequested:
                raise  # user pressed Stop - not a post failure
            except AuthError as exc:
                # Token/permission/checkpoint problem: pointless and risky to keep
                # firing the rest of the queue. Mark this one and abort the loop.
                self.mark(post, STATUS_FAILED, str(exc))
                ran.append(post)
                log.error("인증/보안 오류로 스케줄러 중단: %s", exc)
                raise
            except Exception as exc:  # noqa: BLE001 - recorded per post, loop continues
                log.exception("예약 발행 실패: '%s' - %s", post.topic, exc)
                self.mark(post, STATUS_FAILED, str(exc))
                ran.append(post)
        return ran

    def run_forever(self, control, runner: Callable[[ScheduledPost], object], *,
                    poll_sec: Optional[float] = None,
                    clock: Optional[Callable[[], datetime]] = None) -> None:
        """Tick loop for the worker thread: checkpoint -> run due -> sleep."""
        poll = config.STATUS_POLL_SEC if poll_sec is None else poll_sec
        now_fn = clock or self._clock
        log.info("스케줄러 시작 (폴링 %ss, 지터 +/-%d분)", poll, self.jitter_min)
        while True:
            control.checkpoint()
            self.run_due(runner, now=now_fn(), control=control)
            control.sleep(poll)
