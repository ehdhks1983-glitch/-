"""Image acquisition + ratio processing.

Two sources (spec Stage 4):
   a) AI generation via an injected image provider (OpenAI).
  b) User-supplied file.

Both are normalised to an Instagram-correct ratio:
  * thumbnail -> 1:1
  * feed      -> 4:5 (or 1:1)
  * reels     -> 9:16 (cover frame)

Center-crop to the target aspect, then resize to the exact pixel target, then
save as JPEG (RGB).  Pure Pillow - fully unit-testable.
"""

from __future__ import annotations

import io
import time
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image

import config
import paths
from core.logging_setup import get_logger

log = get_logger("image")

# media_type -> ratio string in config
_MEDIA_RATIO = {
    "thumbnail": config.THUMBNAIL_RATIO,
    "feed": config.FEED_RATIO,
    "image": config.FEED_RATIO,
    "carousel": config.FEED_RATIO,
    "reels": config.REELS_RATIO,
}


def media_dir() -> Path:
    d = paths.appdata_dir() / "media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ratio_for(media_type: str) -> str:
    return _MEDIA_RATIO.get((media_type or "feed").lower(), config.FEED_RATIO)


def ratio_aspect(ratio: str) -> float:
    w, h = ratio.split(":")
    return float(w) / float(h)


def fit_to_ratio(img: Image.Image, ratio: str) -> Image.Image:
    """Center-crop ``img`` to ``ratio`` then resize to the configured pixels."""
    if ratio not in config.RATIO_PIXELS:
        raise ValueError(f"지원하지 않는 비율: {ratio}")
    tw, th = config.RATIO_PIXELS[ratio]
    target = tw / th
    w, h = img.size
    if w == 0 or h == 0:
        raise ValueError("빈 이미지입니다.")
    cur = w / h
    if cur > target:                         # too wide -> trim sides
        new_w = max(1, int(round(h * target)))
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:                                    # too tall -> trim top/bottom
        new_h = max(1, int(round(w / target)))
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    cropped = img.crop(box)
    return cropped.resize((tw, th), Image.Resampling.LANCZOS)


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


class ImageEngine:
    """Produce Instagram-ready JPEGs from AI or user uploads."""

    def __init__(self, store=None, image_provider=None) -> None:
        self.store = store
        self.image_provider = image_provider

    def _save(self, img: Image.Image, out_path: Optional[Path]) -> str:
        img = _to_rgb(img)
        if out_path is None:
            out_path = media_dir() / f"img_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="JPEG", quality=90, optimize=True)
        log.info("이미지 저장: %s (%dx%d)", out_path.name, img.width, img.height)
        return str(out_path)

    def from_upload(self, src_path: str, media_type: str = "feed",
                    out_path: Optional[Path] = None) -> str:
        """Process a user-supplied image to the correct ratio."""
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {src_path}")
        with Image.open(src) as img:
            img.load()
            processed = fit_to_ratio(img, ratio_for(media_type))
        return self._save(processed, out_path)

    def from_ai(self, prompt: str, media_type: str = "feed",
                out_path: Optional[Path] = None) -> str:
        """Generate an image via the injected provider, then ratio-correct it."""
        if self.image_provider is None:
            raise RuntimeError("이미지 프로바이더가 설정되지 않았습니다.")
        ratio = ratio_for(media_type)
        tw, th = config.RATIO_PIXELS[ratio]
        raw = self.image_provider.generate(prompt, size=self._provider_size(ratio))
        img = Image.open(io.BytesIO(raw))
        img.load()
        processed = fit_to_ratio(img, ratio)
        return self._save(processed, out_path)

    @staticmethod
    def _provider_size(ratio: str) -> str:
        # OpenAI image sizes are limited; pick the closest supported aspect.
        return {
            "1:1": "1024x1024",
            "4:5": "1024x1024",
            "9:16": "1024x1792",
            "1.91:1": "1792x1024",
        }.get(ratio, "1024x1024")
