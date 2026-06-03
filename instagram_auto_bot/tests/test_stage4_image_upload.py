"""Stage 4 - image ratio processing + public-URL uploader (retry/fallback/verify)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

import config
from core import image_engine as ie
from core.image_engine import ImageEngine, fit_to_ratio, ratio_for
from core.settings_store import SettingsStore
from core.uploader import HostProvider, UploadError, Uploader, get_host_provider, verify_public_url


def png_bytes(w: int, h: int, color=(12, 34, 56)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Ratio processing
# --------------------------------------------------------------------------- #
def test_ratio_for_media_types():
    assert ratio_for("thumbnail") == config.THUMBNAIL_RATIO
    assert ratio_for("feed") == config.FEED_RATIO
    assert ratio_for("reels") == config.REELS_RATIO
    assert ratio_for("unknown") == config.FEED_RATIO


@pytest.mark.parametrize("size,ratio", [
    ((2000, 500), "1:1"),
    ((800, 600), "4:5"),
    ((600, 600), "9:16"),
    ((1920, 1080), "4:5"),
])
def test_fit_to_ratio_hits_exact_target(size, ratio):
    img = Image.new("RGB", size, (1, 2, 3))
    out = fit_to_ratio(img, ratio)
    assert out.size == config.RATIO_PIXELS[ratio]


def test_fit_to_ratio_rejects_unknown_ratio():
    with pytest.raises(ValueError):
        fit_to_ratio(Image.new("RGB", (10, 10)), "3:2")  # blog ratio not supported on IG


# --------------------------------------------------------------------------- #
# ImageEngine: user upload + AI
# --------------------------------------------------------------------------- #
def test_from_upload_produces_feed_jpeg(tmp_home, tmp_path):
    src = tmp_path / "src.png"
    Image.new("RGBA", (1600, 900), (200, 100, 50, 255)).save(src)
    engine = ImageEngine(store=SettingsStore().load())
    out = engine.from_upload(str(src), media_type="feed")
    with Image.open(out) as img:
        assert img.size == config.RATIO_PIXELS["4:5"]
        assert img.format == "JPEG"
        assert img.mode == "RGB"


def test_from_upload_reels_ratio(tmp_home, tmp_path):
    src = tmp_path / "tall.png"
    Image.new("RGB", (1000, 1000), (0, 0, 0)).save(src)
    out = ImageEngine().from_upload(str(src), media_type="reels")
    with Image.open(out) as img:
        assert img.size == config.RATIO_PIXELS["9:16"]


def test_from_upload_missing_file(tmp_home):
    with pytest.raises(FileNotFoundError):
        ImageEngine().from_upload("/no/such/file.png")


class FakeImageProvider:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, size: str = "1024x1024") -> bytes:
        self.calls.append((prompt, size))
        w, h = (int(x) for x in size.split("x"))
        return png_bytes(w, h)


def test_from_ai_generates_and_ratio_corrects(tmp_home):
    prov = FakeImageProvider()
    engine = ImageEngine(store=SettingsStore().load(), image_provider=prov)
    out = engine.from_ai("아침 햇살이 비치는 책상", media_type="reels")
    with Image.open(out) as img:
        assert img.size == config.RATIO_PIXELS["9:16"]
    assert prov.calls[0][0] == "아침 햇살이 비치는 책상"
    assert prov.calls[0][1] == "1024x1792"      # provider size mapped from 9:16


def test_from_ai_without_provider_raises(tmp_home):
    with pytest.raises(RuntimeError):
        ImageEngine().from_ai("prompt")


# --------------------------------------------------------------------------- #
# Uploader orchestration
# --------------------------------------------------------------------------- #
class FakeHost(HostProvider):
    def __init__(self, name, behavior):
        self.name = name
        self._behavior = list(behavior)   # list of ("url", str) | ("raise", exc)
        self.calls = 0

    def upload(self, file_path: str) -> str:
        self.calls += 1
        kind, val = self._behavior.pop(0) if self._behavior else ("url", f"https://x/{self.name}")
        if kind == "raise":
            raise val
        return val


def _uploader(tmp_home, primary, fallback, verifier):
    return Uploader(SettingsStore().load(), primary=primary, fallback=fallback,
                    verifier=verifier, sleep=lambda s: None, retries=2)


def test_upload_success_primary(tmp_home):
    primary = FakeHost("cloudinary", [("url", "https://cdn/good.jpg")])
    up = _uploader(tmp_home, primary, None, verifier=lambda u: True)
    assert up.upload("/tmp/x.jpg") == "https://cdn/good.jpg"
    assert primary.calls == 1


def test_upload_falls_back_when_primary_errors(tmp_home):
    primary = FakeHost("cloudinary", [("raise", UploadError("creds")), ("raise", UploadError("creds"))])
    fallback = FakeHost("imgbb", [("url", "https://imgbb/ok.jpg")])
    up = _uploader(tmp_home, primary, fallback, verifier=lambda u: True)
    assert up.upload("/tmp/x.jpg") == "https://imgbb/ok.jpg"
    assert primary.calls == 2 and fallback.calls == 1   # exhausted retries, then fell back


def test_upload_falls_back_when_url_unverifiable(tmp_home):
    primary = FakeHost("cloudinary", [("url", "https://bad/x"), ("url", "https://bad/x")])
    fallback = FakeHost("imgbb", [("url", "https://good/x")])
    up = _uploader(tmp_home, primary, fallback, verifier=lambda u: "good" in u)
    assert up.upload("/tmp/x.jpg") == "https://good/x"


def test_upload_all_fail_raises(tmp_home):
    primary = FakeHost("cloudinary", [("raise", UploadError("a")), ("raise", UploadError("a"))])
    fallback = FakeHost("imgbb", [("raise", UploadError("b")), ("raise", UploadError("b"))])
    up = _uploader(tmp_home, primary, fallback, verifier=lambda u: True)
    with pytest.raises(UploadError):
        up.upload("/tmp/x.jpg")


def test_verify_public_url_rejects_non_http():
    assert verify_public_url("") is False
    assert verify_public_url("ftp://host/file") is False


def test_get_host_provider_types(tmp_home):
    store = SettingsStore().load()
    assert get_host_provider("cloudinary", store).__class__.__name__ == "CloudinaryHost"
    assert get_host_provider("imgbb", store).__class__.__name__ == "ImgbbHost"
    with pytest.raises(ValueError):
        get_host_provider("dropbox", store)
