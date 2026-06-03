"""Stage 7 - error classification, friendly messages, scheduler safety."""

from __future__ import annotations

import random
from datetime import datetime

import pytest

from core.automation_controller import JobControl, StopRequested
from core.content_engine import ContentRuleError
from core.errors import humanize, is_auth_error, is_security_checkpoint
from core.instagram_api import (
    AuthError,
    InstagramAPI,
    InstagramAPIError,
    MediaNotReadyError,
    RateLimitError,
    SecurityCheckpointError,
)
from core.publish_flow import ImageSource
from core.scheduler import STATUS_DONE, STATUS_FAILED, STATUS_PENDING, Scheduler
from core.uploader import UploadError
from providers.text_base import ProviderError, ProviderUnavailable


# --------------------------------------------------------------------------- #
# Error classification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("code,expected", [
    (190, AuthError),
    (10, AuthError),
    (200, AuthError),
    (4, RateLimitError),
    (9007, MediaNotReadyError),
    (100, InstagramAPIError),
])
def test_error_code_mapping(code, expected):
    err = InstagramAPI._error_for(code, "msg", None, None, 400)
    assert isinstance(err, expected)


def test_checkpoint_subcode_maps_to_security_error():
    err = InstagramAPI._error_for(368, "blocked", 459, "trace", 400)
    assert isinstance(err, SecurityCheckpointError)
    assert is_security_checkpoint(err) and is_auth_error(err)


# --------------------------------------------------------------------------- #
# humanize
# --------------------------------------------------------------------------- #
def test_humanize_messages():
    assert "보안" in humanize(SecurityCheckpointError("x"))
    assert "토큰" in humanize(AuthError("x"))
    assert "한도" in humanize(RateLimitError("x"))
    assert "9007" in humanize(MediaNotReadyError("x"))
    assert "URL" in humanize(UploadError("x"))
    assert "금지어" in humanize(ContentRuleError("x"))
    assert "설치" in humanize(ProviderUnavailable("x"))
    assert "AI" in humanize(ProviderError("x"))
    assert humanize(Exception("weird")).startswith("오류가 발생")


# --------------------------------------------------------------------------- #
# Scheduler safety: abort on auth, continue on generic, never swallow Stop
# --------------------------------------------------------------------------- #
def _sched(tmp_path):
    return Scheduler(store_path=tmp_path / "s.json", jitter_min=0,
                     rng=random.Random(0), clock=lambda: datetime(2026, 6, 3, 12, 0, 0))


def test_run_due_aborts_on_auth_error(tmp_path):
    s = _sched(tmp_path)
    p1 = s.add(datetime(2026, 6, 3, 10, 0, 0), "first", "image", [ImageSource("ai")])
    p2 = s.add(datetime(2026, 6, 3, 11, 0, 0), "second", "image", [ImageSource("ai")])

    def runner(post):
        if post.topic == "first":
            raise AuthError("token expired", code=190)

    with pytest.raises(AuthError):
        s.run_due(runner)
    assert p1.status == STATUS_FAILED
    assert p2.status == STATUS_PENDING        # loop aborted before reaching it


def test_run_due_continues_on_generic_error(tmp_path):
    s = _sched(tmp_path)
    p1 = s.add(datetime(2026, 6, 3, 10, 0, 0), "first", "image", [ImageSource("ai")])
    p2 = s.add(datetime(2026, 6, 3, 11, 0, 0), "second", "image", [ImageSource("ai")])

    def runner(post):
        if post.topic == "first":
            raise ValueError("transient-ish")

    s.run_due(runner)
    assert p1.status == STATUS_FAILED
    assert p2.status == STATUS_DONE           # generic error does not abort queue


def test_run_due_does_not_swallow_stop(tmp_path):
    s = _sched(tmp_path)
    p = s.add(datetime(2026, 6, 3, 10, 0, 0), "x", "image", [ImageSource("ai")])
    control = JobControl()

    def runner(post):
        control.request_stop()
        control.checkpoint()                  # raises StopRequested

    with pytest.raises(StopRequested):
        s.run_due(runner, control=control)
    assert p.status == STATUS_PENDING          # not marked failed on user-stop
