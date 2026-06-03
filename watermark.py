"""
watermark.py — 전역 워터마크 (블로그 ID/로고 자동 삽입)
설정은 data/watermark.json 에 저장되고, 모든 변환 결과(이미지합치기/편집/쇼츠/영상)에
자동으로 적용됩니다.
  - PIL 경로(이미지합치기·편집·쇼츠): 텍스트 + 로고 이미지 모두 지원
  - 영상(ffmpeg) 경로: 텍스트 워터마크(drawtext) 지원
"""

import json
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from config import DATA_DIR
from editor import _load_text_font

WM_FILE = DATA_DIR / "watermark.json"

# 위치: 한글 표시명 ↔ 내부 키
POSITION_NAMES = {
    "우측 하단": "br", "우측 상단": "tr",
    "좌측 하단": "bl", "좌측 상단": "tl", "가운데": "center",
}
KEY_TO_NAME = {v: k for k, v in POSITION_NAMES.items()}
MODE_NAMES = {"텍스트": "text", "로고 이미지": "image", "둘 다": "both"}
NAME_TO_MODE = {v: k for k, v in MODE_NAMES.items()}

DEFAULTS = {
    "enabled": False,
    "mode": "text",          # text / image / both
    "text": "",
    "text_color": "#FFFFFF",
    "image_path": "",
    "position": "br",
    "scale": 18,             # 로고 크기 (영상/이미지 폭 대비 %)
    "opacity": 70,           # 투명도 %
    "margin": 4,             # 가장자리 여백 (폭 대비 %)
}


class Watermark:
    """워터마크 설정 (JSON 영속)"""
    def __init__(self):
        self._d = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            if WM_FILE.exists():
                self._d.update(json.loads(WM_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass

    def save(self):
        try:
            WM_FILE.parent.mkdir(parents=True, exist_ok=True)
            WM_FILE.write_text(json.dumps(self._d, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        except Exception:
            pass

    def get(self, key, default=None):
        v = self._d.get(key)
        return v if v is not None else (DEFAULTS.get(key) if default is None else default)

    def set(self, key, value):
        self._d[key] = value

    @property
    def active(self) -> bool:
        if not self._d.get("enabled"):
            return False
        m = self._d.get("mode", "text")
        if m in ("text", "both") and (self._d.get("text") or "").strip():
            return True
        if m in ("image", "both"):
            p = self._d.get("image_path") or ""
            if p and Path(p).exists():
                return True
        return False


watermark = Watermark()  # 전역 싱글턴
_logo_cache: dict = {}


def _load_logo(path: str) -> Optional[Image.Image]:
    if not path or not Path(path).exists():
        return None
    try:
        if path not in _logo_cache:
            _logo_cache[path] = Image.open(path).convert("RGBA")
        return _logo_cache[path]
    except Exception:
        return None


def _paste_positioned(base: Image.Image, layer: Image.Image, pos: str, margin: int):
    fw, fh = base.size
    lw, lh = layer.size
    if pos == "tl":
        x, y = margin, margin
    elif pos == "tr":
        x, y = fw - lw - margin, margin
    elif pos == "bl":
        x, y = margin, fh - lh - margin
    elif pos == "center":
        x, y = (fw - lw) // 2, (fh - lh) // 2
    else:  # br
        x, y = fw - lw - margin, fh - lh - margin
    base.alpha_composite(layer, (max(0, x), max(0, y)))


def apply_to_frame(frame: Image.Image) -> Image.Image:
    """PIL 프레임에 워터마크(텍스트+로고) 합성. 비활성 시 원본 그대로."""
    if not watermark.active:
        return frame
    try:
        in_mode = frame.mode
        base = frame.convert("RGBA")
        fw, fh = base.size
        opacity = max(0, min(100, int(watermark.get("opacity")))) / 100.0
        margin = max(2, int(fw * float(watermark.get("margin")) / 100))
        pos = watermark.get("position", "br")
        mode = watermark.get("mode", "text")

        # 로고 이미지
        if mode in ("image", "both"):
            logo = _load_logo(watermark.get("image_path"))
            if logo:
                scale = max(2, int(watermark.get("scale"))) / 100.0
                lw = max(1, int(fw * scale))
                lh = max(1, int(logo.height * lw / logo.width))
                lg = logo.resize((lw, lh), Image.LANCZOS).convert("RGBA")
                if opacity < 1.0:
                    a = lg.split()[3].point(lambda v: int(v * opacity))
                    lg.putalpha(a)
                _paste_positioned(base, lg, pos, margin)

        # 텍스트
        if mode in ("text", "both"):
            txt = (watermark.get("text") or "").strip()
            if txt:
                size = max(14, int(fw * 0.045))
                font = _load_text_font(size, bold=True)
                tmp = ImageDraw.Draw(base)
                bbox = tmp.textbbox((0, 0), txt, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                pad = max(4, size // 4)
                tlayer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
                td = ImageDraw.Draw(tlayer)
                ox, oy = pad - bbox[0], pad - bbox[1]
                bw = max(1, size // 12)
                for dx in range(-bw, bw + 1):
                    for dy in range(-bw, bw + 1):
                        if dx or dy:
                            td.text((ox + dx, oy + dy), txt, font=font, fill=(0, 0, 0, 230))
                td.text((ox, oy), txt, font=font, fill=watermark.get("text_color", "#FFFFFF"))
                if opacity < 1.0:
                    a = tlayer.split()[3].point(lambda v: int(v * opacity))
                    tlayer.putalpha(a)
                _paste_positioned(base, tlayer, pos, margin)

        return base.convert("RGB") if in_mode == "RGB" else base
    except Exception:
        return frame


def _wm_font_path() -> str:
    if sys.platform == "win32":
        return "C\\:/Windows/Fonts/malgunbd.ttf"
    for p in ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists():
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def drawtext_filter(video_height: int = 480) -> str:
    """영상(ffmpeg)용 텍스트 워터마크 drawtext 필터. (로고 이미지는 영상 미지원)"""
    if not watermark.active:
        return ""
    mode = watermark.get("mode", "text")
    if mode not in ("text", "both"):
        return ""
    txt = (watermark.get("text") or "").strip()
    if not txt:
        return ""
    size = max(12, int(video_height * 0.045))
    col = watermark.get("text_color", "#FFFFFF").replace("#", "0x")
    opacity = max(0, min(100, int(watermark.get("opacity")))) / 100.0
    margin = max(4, int(video_height * float(watermark.get("margin")) / 100))
    pos = watermark.get("position", "br")
    if pos == "tl":
        x, y = f"{margin}", f"{margin}"
    elif pos == "tr":
        x, y = f"w-tw-{margin}", f"{margin}"
    elif pos == "bl":
        x, y = f"{margin}", f"h-th-{margin}"
    elif pos == "center":
        x, y = "(w-tw)/2", "(h-th)/2"
    else:  # br
        x, y = f"w-tw-{margin}", f"h-th-{margin}"
    esc = (txt.replace("\\", "\\\\").replace(":", "\\:")
           .replace("'", "\\'").replace("%", "\\%"))
    bw = max(1, size // 12)
    return (f"drawtext=text='{esc}':fontfile='{_wm_font_path()}':fontsize={size}:"
            f"fontcolor={col}@{opacity:.2f}:borderw={bw}:bordercolor=black@{opacity:.2f}:"
            f"x={x}:y={y}")
