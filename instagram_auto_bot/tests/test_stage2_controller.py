"""Stage 2 - async control state machine, log queue, form specs (all Tk-free)."""

from __future__ import annotations

import threading
import time

import pytest

from core.automation_controller import (
    AutomationController,
    JobControl,
    StopRequested,
    WorkerState,
)
from core.forms import ACCOUNT_FIELDS, BRAND_FIELDS, FieldSpec, default_for
from core.settings_store import DEFAULT_SETTINGS, SECRET_KEYS
from core.ui_bridge import LogQueue


def _wait(predicate, timeout=2.0, interval=0.01):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return False


# --------------------------------------------------------------------------- #
# JobControl
# --------------------------------------------------------------------------- #
def test_jobcontrol_checkpoint_and_stop():
    ctrl = JobControl()
    ctrl.checkpoint()                # no-op when neither paused nor stopping
    ctrl.request_stop()
    assert ctrl.stopping is True
    with pytest.raises(StopRequested):
        ctrl.checkpoint()


def test_jobcontrol_sleep_is_interruptible():
    ctrl = JobControl()
    start = time.monotonic()
    ctrl.sleep(0.05)
    assert time.monotonic() - start >= 0.04

    ctrl.request_stop()
    with pytest.raises(StopRequested):
        ctrl.sleep(5.0)              # must not actually wait 5s


# --------------------------------------------------------------------------- #
# AutomationController
# --------------------------------------------------------------------------- #
def test_runs_target_and_reports_done():
    states: list[WorkerState] = []
    ctrl = AutomationController(on_state_change=states.append)
    done: list[int] = []

    def target(control, x):
        control.checkpoint()
        return x * 2

    assert ctrl.start(target, 21, on_done=done.append) is True
    assert _wait(lambda: done == [42])
    assert _wait(lambda: ctrl.state == WorkerState.IDLE)
    assert WorkerState.RUNNING in states and states[-1] == WorkerState.IDLE


def test_pause_freezes_progress_then_resume():
    ctrl = AutomationController()
    counter = {"n": 0}
    started = threading.Event()

    def target(control):
        while True:
            control.checkpoint()
            counter["n"] += 1
            started.set()
            control.sleep(0.01)

    ctrl.start(target)
    assert started.wait(2.0)
    ctrl.pause()
    assert _wait(lambda: ctrl.state == WorkerState.PAUSED)
    time.sleep(0.1)
    a = counter["n"]
    time.sleep(0.15)
    b = counter["n"]
    assert a == b, "counter advanced while paused"

    ctrl.resume()
    assert _wait(lambda: counter["n"] > b)
    ctrl.stop(wait=True, timeout=2.0)
    assert _wait(lambda: ctrl.state == WorkerState.IDLE)
    assert ctrl.is_active is False


def test_stop_unwinds_cleanly():
    ctrl = AutomationController()
    ended = {"clean": False}
    running = threading.Event()

    def target(control):
        try:
            while True:
                control.checkpoint()
                running.set()
                control.sleep(0.02)
        except StopRequested:
            ended["clean"] = True
            raise

    ctrl.start(target)
    assert running.wait(2.0)
    ctrl.stop(wait=True, timeout=2.0)
    assert ended["clean"] is True
    assert ctrl.state == WorkerState.IDLE


def test_double_start_is_rejected():
    ctrl = AutomationController()
    release = threading.Event()

    def target(control):
        release.wait(2.0)

    assert ctrl.start(target) is True
    assert _wait(lambda: ctrl.state == WorkerState.RUNNING)
    assert ctrl.start(target) is False    # already active
    release.set()
    ctrl.join(2.0)


def test_on_error_called_and_no_done():
    ctrl = AutomationController()
    errors: list[BaseException] = []
    done: list = []

    def target(control):
        raise ValueError("boom")

    ctrl.start(target, on_error=errors.append, on_done=done.append)
    assert _wait(lambda: len(errors) == 1)
    assert isinstance(errors[0], ValueError)
    assert done == []                     # on_done skipped on error
    assert _wait(lambda: ctrl.state == WorkerState.IDLE)


# --------------------------------------------------------------------------- #
# LogQueue
# --------------------------------------------------------------------------- #
def test_logqueue_fifo_and_drain_limit():
    q = LogQueue()
    for i in range(5):
        q.push(f"line{i}")
    assert len(q) == 5
    first_two = q.drain(max_items=2)
    assert first_two == ["line0", "line1"]
    rest = q.drain()
    assert rest == ["line2", "line3", "line4"]
    assert q.drain() == []


def test_logqueue_overflow_drops_oldest():
    q = LogQueue(maxsize=3)
    for i in range(5):
        q.push(str(i))
    drained = q.drain()
    assert drained == ["2", "3", "4"]     # oldest two dropped


# --------------------------------------------------------------------------- #
# Form specs
# --------------------------------------------------------------------------- #
def test_every_field_maps_to_a_real_setting():
    for spec in (*ACCOUNT_FIELDS, *BRAND_FIELDS):
        assert isinstance(spec, FieldSpec)
        assert spec.key in DEFAULT_SETTINGS, f"{spec.key} missing from settings"


def test_user_entered_secrets_are_masked():
    secret_field_keys = {s.key for s in ACCOUNT_FIELDS if s.secret}
    # Every user-entered secret key is represented as a masked field.
    assert secret_field_keys == set(SECRET_KEYS)
    # And nothing marked secret leaks as a plain field.
    for spec in ACCOUNT_FIELDS:
        if spec.key in SECRET_KEYS:
            assert spec.secret is True


def test_provider_defaults_within_options():
    by_key = {s.key: s for s in ACCOUNT_FIELDS}
    assert default_for(by_key["text_provider"]) in by_key["text_provider"].options
    assert default_for(by_key["host_provider"]) in by_key["host_provider"].options
