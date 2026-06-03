"""Stage 5 - Graph API publish flow, daily guard, token manager, pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import requests

import config
from core.content_engine import PostDraft
from core.instagram_api import (
    DailyPostGuard,
    InstagramAPI,
    InstagramAPIError,
    MediaNotReadyError,
    PublishResult,
    RateLimitError,
)
from core.publish_flow import ImageSource, PreparedPost, PublishPipeline
from core.settings_store import SettingsStore
from core.token_manager import TokenManager

RAISE_NETWORK = object()


class FakeResp:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # (method, url, params)

    def request(self, method, url, params=None, timeout=None, **kw):
        self.calls.append((method, url, dict(params or {})))
        item = self.responses.pop(0) if self.responses else FakeResp(
            {"error": {"code": -1, "message": "exhausted"}}, 400)
        if item is RAISE_NETWORK:
            raise requests.ConnectionError("simulated network error")
        return item


def ok(data):
    return FakeResp(data, 200)


def err(code, msg, status=400):
    return FakeResp({"error": {"code": code, "message": msg}}, status)


def _api(session, **kw):
    opts = dict(session=session, sleep=lambda *_: None, poll_interval=0, poll_max=5, retries=3)
    opts.update(kw)
    return InstagramAPI("TOKEN", "123", **opts)


# --------------------------------------------------------------------------- #
# Image publish + polling
# --------------------------------------------------------------------------- #
def test_publish_image_happy_path():
    session = FakeSession([
        ok({"id": "C1"}),                       # create container
        ok({"status_code": "IN_PROGRESS"}),     # poll 1
        ok({"status_code": "FINISHED"}),        # poll 2
        ok({"id": "M1"}),                       # publish
        ok({"permalink": "https://insta/p/abc"}),
    ])
    api = _api(session)
    res = api.publish_image("https://img/x.jpg", "캡션")

    assert isinstance(res, PublishResult)
    assert res.media_id == "M1" and res.container_id == "C1"
    assert res.permalink.endswith("abc")
    # access_token auto-attached; container created with image_url.
    create = session.calls[0]
    assert create[0] == "POST" and create[1].endswith("/123/media")
    assert create[2]["image_url"] == "https://img/x.jpg"
    assert create[2]["access_token"] == "TOKEN"
    # polled exactly twice (IN_PROGRESS then FINISHED).
    polls = [c for c in session.calls if c[1].endswith("/C1") and c[2].get("fields") == "status_code"]
    assert len(polls) == 2


def test_publish_times_out_when_never_finished():
    session = FakeSession([ok({"id": "C1"})] + [ok({"status_code": "IN_PROGRESS"})] * 5)
    api = _api(session, poll_max=2)
    with pytest.raises(InstagramAPIError):
        api.publish_image("https://img/x.jpg", "c")


def test_container_error_status_raises():
    session = FakeSession([ok({"id": "C1"}), ok({"status_code": "ERROR"})])
    with pytest.raises(InstagramAPIError):
        _api(session).publish_image("https://img/x.jpg", "c")


def test_9007_triggers_repoll_then_publishes():
    session = FakeSession([
        ok({"id": "C1"}),
        ok({"status_code": "FINISHED"}),
        err(config.ERR_MEDIA_NOT_READY, "Media not ready"),  # publish too early
        ok({"status_code": "FINISHED"}),                     # re-poll
        ok({"id": "M1"}),                                    # publish succeeds
        ok({"permalink": "https://insta/p/ok"}),
    ])
    res = _api(session).publish_image("https://img/x.jpg", "c")
    assert res.media_id == "M1"


def test_transient_error_is_retried():
    session = FakeSession([
        err(4, "rate limited"),     # transient -> retry
        ok({"id": "C1"}),
        ok({"status_code": "FINISHED"}),
        ok({"id": "M1"}),
        ok({"permalink": "https://insta/p/x"}),
    ])
    res = _api(session).publish_image("https://img/x.jpg", "c")
    assert res.media_id == "M1"
    create_calls = [c for c in session.calls if c[1].endswith("/123/media")]
    assert len(create_calls) == 2  # one failed (transient) + one success


def test_permanent_error_raises_immediately():
    session = FakeSession([err(100, "Invalid parameter")])
    with pytest.raises(InstagramAPIError):
        _api(session).create_image_container("https://img/x.jpg", "c")


def test_network_error_is_retried():
    session = FakeSession([RAISE_NETWORK, ok({"id": "C9"})])
    assert _api(session).create_image_container("https://img/x.jpg") == "C9"


def test_carousel_publish_and_validation():
    session = FakeSession([
        ok({"id": "ch1"}),
        ok({"id": "ch2"}),
        ok({"id": "C1"}),
        ok({"status_code": "FINISHED"}),
        ok({"id": "M1"}),
        ok({"permalink": "https://insta/p/car"}),
    ])
    api = _api(session)
    res = api.publish_carousel(["u1", "u2"], "cap")
    assert res.media_id == "M1"
    container_call = [c for c in session.calls if c[2].get("media_type") == "CAROUSEL"][0]
    assert container_call[2]["children"] == "ch1,ch2"

    with pytest.raises(ValueError):
        api.publish_carousel(["only-one"], "cap")  # min 2


# --------------------------------------------------------------------------- #
# Daily post guard
# --------------------------------------------------------------------------- #
def test_daily_guard_blocks_after_max(tmp_path):
    now = {"t": datetime(2026, 6, 3, 9, 0, 0)}
    guard = DailyPostGuard(max_per_day=2, counts_path=tmp_path / "counts.json",
                           clock=lambda: now["t"])
    assert guard.remaining() == 2
    guard.check(); guard.record()
    guard.check(); guard.record()
    assert guard.remaining() == 0
    with pytest.raises(RateLimitError):
        guard.check()
    # next day resets.
    now["t"] = datetime(2026, 6, 4, 9, 0, 0)
    assert guard.remaining() == 2
    guard.check()


# --------------------------------------------------------------------------- #
# Token manager
# --------------------------------------------------------------------------- #
def test_token_lifecycle(tmp_home):
    now = {"t": datetime(2026, 6, 3, 12, 0, 0)}
    store = SettingsStore().load()
    tm = TokenManager(store, clock=lambda: now["t"])

    assert tm.needs_refresh() is False                 # no token yet
    tm.set_token("LL_TOKEN", lifetime_days=60, persist=False)
    assert 59 < tm.days_until_expiry() <= 60
    assert tm.needs_refresh() is False                 # 60d > 7d window

    now["t"] = datetime(2026, 7, 31, 12, 0, 0)         # ~3 days before expiry
    assert tm.needs_refresh() is True
    now["t"] = datetime(2026, 8, 5, 12, 0, 0)          # past expiry
    assert tm.is_expired() is True


def test_token_present_but_no_expiry_needs_refresh(tmp_home):
    store = SettingsStore().load()
    store.set("ig_access_token", "X")
    assert TokenManager(store).needs_refresh() is True


class FakeHTTP:
    def __init__(self, data, raise_exc=None):
        self._data = data
        self._raise = raise_exc

    def get(self, url, params=None, timeout=None):
        if self._raise:
            raise self._raise
        return FakeResp(self._data)


def test_token_refresh_success(tmp_home):
    now = {"t": datetime(2026, 6, 3, 12, 0, 0)}
    store = SettingsStore().load()
    store.set("ig_access_token", "OLD")
    tm = TokenManager(store, session=FakeHTTP({"access_token": "NEW", "expires_in": 5184000}),
                      clock=lambda: now["t"])
    assert tm.refresh(persist=False) is True
    assert store.get_str("ig_access_token") == "NEW"
    assert 59 < tm.days_until_expiry() <= 60


def test_token_refresh_failure_keeps_old(tmp_home):
    store = SettingsStore().load()
    store.set("ig_access_token", "OLD")
    tm = TokenManager(store, session=FakeHTTP({"error": "bad"}))
    assert tm.refresh(persist=False) is False
    assert store.get_str("ig_access_token") == "OLD"

    tm2 = TokenManager(store, session=FakeHTTP(None, raise_exc=requests.ConnectionError("x")))
    assert tm2.refresh(persist=False) is False


# --------------------------------------------------------------------------- #
# Publish pipeline (prepare -> approve -> publish)
# --------------------------------------------------------------------------- #
class FakeContentEngine:
    def __init__(self):
        self.calls = []

    def generate(self, topic, media_type="image"):
        self.calls.append((topic, media_type))
        return PostDraft(topic, media_type, "제목", "기획", "본문 내용",
                         ["#하나", "#둘", "#셋", "#넷", "#다섯"])


class FakeImageEngine:
    def __init__(self):
        self.ai = []
        self.uploads = []

    def from_ai(self, prompt, media_type="feed"):
        self.ai.append((prompt, media_type))
        return f"/tmp/ai_{len(self.ai)}.jpg"

    def from_upload(self, path, media_type="feed"):
        self.uploads.append((path, media_type))
        return f"/tmp/up_{len(self.uploads)}.jpg"


class FakeUploader:
    def __init__(self):
        self.uploaded = []

    def upload(self, path):
        self.uploaded.append(path)
        return f"https://cdn/{path.split('/')[-1]}"


class FakeAPI:
    def __init__(self):
        self.image = self.carousel = self.reels = 0

    def publish_image(self, url, caption, *, control=None):
        self.image += 1
        return PublishResult("MI", "CI", "https://insta/p/i")

    def publish_carousel(self, urls, caption, *, control=None):
        self.carousel += 1
        return PublishResult("MC", "CC", "https://insta/p/c")

    def publish_reels(self, url, caption, *, control=None):
        self.reels += 1
        return PublishResult("MR", "CR", "https://insta/p/r")


def _pipeline(api=None, guard=None):
    return PublishPipeline(content_engine=FakeContentEngine(), image_engine=FakeImageEngine(),
                           uploader=FakeUploader(), api=api, guard=guard)


def test_prepare_ai_single_image():
    p = _pipeline()
    prepared = p.prepare("아침 루틴", "image", [ImageSource("ai", prompt="밝은 책상")])
    assert isinstance(prepared, PreparedPost)
    assert len(prepared.public_urls) == 1
    assert prepared.public_urls[0].startswith("https://cdn/")
    assert prepared.caption  # composed from draft
    assert p.image_engine.ai == [("밝은 책상", "image")]


def test_prepare_upload_multiple_images():
    p = _pipeline()
    prepared = p.prepare("주제", "carousel",
                         [ImageSource("upload", path="/a.png"), ImageSource("upload", path="/b.png")])
    assert len(prepared.public_urls) == 2
    assert p.uploader.uploaded == ["/tmp/up_1.jpg", "/tmp/up_2.jpg"]


def test_publish_routes_image_and_records_guard(tmp_path):
    api = FakeAPI()
    guard = DailyPostGuard(max_per_day=5, counts_path=tmp_path / "c.json")
    p = _pipeline(api=api, guard=guard)
    prepared = PreparedPost(FakeContentEngine().generate("t"), "image",
                            ["https://cdn/x.jpg"])
    res = p.publish(prepared)
    assert res.media_id == "MI" and api.image == 1
    assert guard.count_today() == 1


def test_publish_routes_carousel_and_reels(tmp_path):
    api = FakeAPI()
    p = _pipeline(api=api)
    draft = FakeContentEngine().generate("t")
    p.publish(PreparedPost(draft, "carousel", ["u1", "u2"]))
    p.publish(PreparedPost(draft, "reels", ["v1"]))
    assert api.carousel == 1 and api.reels == 1


def test_publish_blocked_by_guard_does_not_call_api(tmp_path):
    api = FakeAPI()
    now = {"t": datetime(2026, 6, 3)}
    guard = DailyPostGuard(max_per_day=1, counts_path=tmp_path / "c.json", clock=lambda: now["t"])
    guard.record()  # already at cap
    p = _pipeline(api=api, guard=guard)
    with pytest.raises(RateLimitError):
        p.publish(PreparedPost(FakeContentEngine().generate("t"), "image", ["https://cdn/x.jpg"]))
    assert api.image == 0  # never attempted


def test_publish_without_api_raises():
    p = _pipeline(api=None)
    with pytest.raises(RuntimeError):
        p.publish(PreparedPost(FakeContentEngine().generate("t"), "image", ["https://cdn/x.jpg"]))


# --------------------------------------------------------------------------- #
# Service factory wiring (no SDK / no keys required)
# --------------------------------------------------------------------------- #
def test_build_pipeline_without_token_has_no_api(tmp_home):
    from core import app_services
    store = SettingsStore().load()
    pipe = app_services.build_pipeline(store)
    assert pipe.content_engine is not None
    assert pipe.image_engine is not None
    assert pipe.uploader is not None
    assert pipe.api is None            # not publishable yet
    assert pipe.guard is not None


def test_build_pipeline_with_token_has_api(tmp_home):
    from core import app_services
    store = SettingsStore().load()
    store.set("ig_access_token", "T")
    store.set("ig_user_id", "123")
    pipe = app_services.build_pipeline(store)
    assert pipe.api is not None
    assert pipe.api.ig_user_id == "123"
    assert app_services.build_token_manager(store).__class__.__name__ == "TokenManager"
