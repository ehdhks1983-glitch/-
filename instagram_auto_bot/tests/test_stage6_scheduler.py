"""Stage 6 - scheduler: jitter, due-selection, persistence, run loop."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

import config
from core.automation_controller import JobControl, StopRequested
from core.publish_flow import ImageSource
from core.scheduler import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    ScheduledPost,
    Scheduler,
    apply_jitter,
)


def _sched(tmp_path, **kw):
    opts = dict(store_path=tmp_path / "schedule.json", jitter_min=15,
                rng=random.Random(0), clock=lambda: datetime(2026, 6, 3, 12, 0, 0))
    opts.update(kw)
    return Scheduler(**opts)


# --------------------------------------------------------------------------- #
# Jitter
# --------------------------------------------------------------------------- #
def test_jitter_within_bounds():
    base = datetime(2026, 6, 3, 9, 0, 0)
    rng = random.Random(1)
    for _ in range(200):
        out = apply_jitter(base, 15, rng)
        assert abs((out - base).total_seconds()) <= 15 * 60 + 1


def test_jitter_zero_is_noop():
    base = datetime(2026, 6, 3, 9, 0, 0)
    assert apply_jitter(base, 0) == base


def test_jitter_actually_varies():
    base = datetime(2026, 6, 3, 9, 0, 0)
    rng = random.Random(7)
    outs = {apply_jitter(base, 15, rng) for _ in range(20)}
    assert len(outs) > 1  # not a fixed exact-minute cadence


# --------------------------------------------------------------------------- #
# Queue + persistence
# --------------------------------------------------------------------------- #
def test_add_applies_jitter_and_persists(tmp_path):
    s = _sched(tmp_path)
    when = datetime(2026, 6, 3, 18, 0, 0)
    post = s.add(when, "아침 루틴", "image", [ImageSource("ai", prompt="p")])
    assert post.status == STATUS_PENDING
    assert abs((post.effective_at - when).total_seconds()) <= 15 * 60 + 1

    # A fresh Scheduler loads the same queue from disk.
    s2 = _sched(tmp_path)
    loaded = s2.all()
    assert len(loaded) == 1
    assert loaded[0].topic == "아침 루틴"
    assert loaded[0].image_sources[0].mode == "ai"
    assert loaded[0].effective_at == post.effective_at


def test_remove(tmp_path):
    s = _sched(tmp_path)
    p = s.add(datetime(2026, 6, 3, 18, 0, 0), "t", "image", [ImageSource("ai")])
    assert s.remove(p.id) is True
    assert s.all() == []
    assert s.remove("nope") is False


# --------------------------------------------------------------------------- #
# Due selection + execution
# --------------------------------------------------------------------------- #
def test_due_only_returns_past_pending(tmp_path):
    s = _sched(tmp_path, jitter_min=0)
    past = s.add(datetime(2026, 6, 3, 11, 0, 0), "past", "image", [ImageSource("ai")])
    s.add(datetime(2026, 6, 3, 13, 0, 0), "future", "image", [ImageSource("ai")])
    due = s.due()  # clock is 12:00
    assert [p.id for p in due] == [past.id]


def test_run_due_marks_done_and_failed(tmp_path):
    s = _sched(tmp_path, jitter_min=0)
    good = s.add(datetime(2026, 6, 3, 11, 0, 0), "good", "image", [ImageSource("ai")])
    bad = s.add(datetime(2026, 6, 3, 11, 30, 0), "bad", "image", [ImageSource("ai")])

    def runner(post):
        if post.topic == "bad":
            raise RuntimeError("boom")

    ran = s.run_due(runner)
    assert {p.id for p in ran} == {good.id, bad.id}
    assert good.status == STATUS_DONE
    assert bad.status == STATUS_FAILED and "boom" in bad.info
    # persisted statuses survive reload.
    assert {p.status for p in _sched(tmp_path).all()} == {STATUS_DONE, STATUS_FAILED}


def test_run_due_ignores_future(tmp_path):
    s = _sched(tmp_path, jitter_min=0)
    s.add(datetime(2026, 6, 3, 23, 0, 0), "future", "image", [ImageSource("ai")])
    called = []
    s.run_due(lambda p: called.append(p))
    assert called == []


def test_run_forever_loop_runs_due_then_stops(tmp_path):
    s = _sched(tmp_path, jitter_min=0)
    s.add(datetime(2026, 6, 3, 11, 0, 0), "now", "image", [ImageSource("ai")])
    control = JobControl()
    calls = []

    def runner(post):
        calls.append(post.topic)
        control.request_stop()  # stop after first publish

    with pytest.raises(StopRequested):
        s.run_forever(control, runner, poll_sec=0)
    assert calls == ["now"]
