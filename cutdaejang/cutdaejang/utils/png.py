"""의존성 없는 최소 PNG 생성기.

배경 폴백(단색·그라데이션)과 자막 가독성용 하단 그라데이션 오버레이(기획안 §5.3, §5.4의
그라데이션 트랙)를 Pillow 없이 만들기 위한 모듈. RGBA, 무필터(filter type 0)로 기록한다.
"""

from __future__ import annotations

import struct
import zlib
from typing import Callable, Sequence


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png_rows(path: str, width: int, height: int, row_fn: Callable[[int], bytes]) -> str:
    """row_fn(y) → RGBA 바이트열(width*4)을 받아 PNG 파일로 기록."""
    raw = bytearray()
    for y in range(height):
        row = row_fn(y)
        if len(row) != width * 4:
            raise ValueError(f"행 {y} 길이 불일치: {len(row)} != {width * 4}")
        raw.append(0)  # filter type 0 (None)
        raw += row
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8bit RGBA
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(_chunk(b"IEND", b""))
    return path


def _lerp(a: Sequence[int], b: Sequence[int], t: float) -> tuple:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def solid_png(path: str, width: int, height: int, rgb: Sequence[int]) -> str:
    row = bytes((*rgb, 255)) * width
    return write_png_rows(path, width, height, lambda y: row)


def vertical_gradient_png(
    path: str, width: int, height: int, top_rgb: Sequence[int], bottom_rgb: Sequence[int]
) -> str:
    """세로 그라데이션 배경 (오프라인 배경 폴백용)."""

    def row_fn(y: int) -> bytes:
        c = _lerp(top_rgb, bottom_rgb, y / max(1, height - 1))
        return bytes((*c, 255)) * width

    return write_png_rows(path, width, height, row_fn)


def bottom_gradient_overlay_png(
    path: str,
    width: int,
    height: int,
    cover_ratio: float = 0.35,
    max_alpha: int = 165,
) -> str:
    """하단 투명→검정 그라데이션 오버레이 — 자막 가독성 확보용.

    cover_ratio: 화면 아래쪽에서 그라데이션이 차지하는 비율 (기본 35%).
    max_alpha: 최하단 불투명도 (0~255).
    """
    start_y = round(height * (1.0 - cover_ratio))
    transparent = b"\x00\x00\x00\x00" * width

    def row_fn(y: int) -> bytes:
        if y < start_y:
            return transparent
        t = (y - start_y) / max(1, height - 1 - start_y)
        t = t * t * (3 - 2 * t)  # smoothstep — 경계선이 보이지 않게
        return bytes((0, 0, 0, round(max_alpha * t))) * width

    return write_png_rows(path, width, height, row_fn)
