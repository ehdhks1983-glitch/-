"""🧹 영상에 박힌 자막 지우기 (v1.28, 목록 54).

회원님 22차:
> "중국 영상으로 쿠팡파트너스를 많이 하거든? 그래서 자막을 지우고 영상을 제작하는데
>  이 기능이 있으면 좋을 것 같고 … 필요 없는 자막이 있는 경우도 많아서"

원본에 **구워진**(지울 수 없게 화면에 그려진) 자막을 가리고, 그 자리에 우리 한국어
자막을 얹는다. 라이브러리를 새로 붙이지 않고 FFmpeg + 표준 라이브러리만 쓴다.

## 어떻게 찾나
프레임 몇 장을 **흑백 원본 바이트**로 받아(`-f rawvideo -pix_fmt gray`) 가로줄마다 점수를 낸다.
처음엔 «밝은 화소 개수»로 찾으려다 실패했다 — 배경이 밝으면 자막이 묻힌다.
실제로 통한 신호는 **«흰 글자 + 검은 테두리» 때문에 한 줄 안에서 밝기가 급변하는 정도**다.
실측: 자막 줄 383점 vs 나머지 중앙값 1점으로 압도적으로 튄다.
160px로 줄여 보므로 프레임당 45KB — 순수 파이썬으로도 0.2초면 끝난다.

## 어떻게 가리나
`delogo`(주변 색으로 메우기)가 가장 깨끗했다. 실측 비교(720×1280, 6초):
    delogo 0.8초(흔적 없음) · blur 1.0초(얼룩 남음) · 검은 박스 0.8초(띠가 보임)
⚠ 배경이 복잡하면 delogo도 번진 자국이 남는다 → 그 자리에 한국어 자막을 덮는 조합이
실전에서 가장 깔끔하다.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from ..utils import ffmpeg as ff

log = logging.getLogger("cutdaejang")

PROBE_WIDTH = 160        # 이 폭으로 줄여서 본다 (프레임당 45KB — 순수 파이썬으로 충분)
PROBE_FRAMES = 12        # 몇 장을 볼지 (자막이 바뀌는 걸 잡으려면 여러 장)
EDGE_STEP = 70           # 옆 화소와 이만큼 차이 나면 «글자 가장자리»로 센다
PEAK_RATIO = 0.25        # 가장 센 줄의 이 비율 이상인 줄까지 자막으로 본다
SEARCH_FROM = 0.55       # 화면 위에서부터 이 비율 아래쪽만 찾는다 (자막은 아래쪽)
MIN_PEAK = 40            # 이보다 약하면 «자막 없음»으로 본다 (헛디텍션 방지)
PAD_PX = 8               # 찾은 범위 위아래로 이만큼 여유


def _gray_frames(video: str, width: int, height: int,
                 n: int, duration_s: float) -> List[bytes]:
    """프레임 n장을 흑백 원본 바이트로 (디코딩 라이브러리 없이 ffmpeg에게 맡긴다)."""
    fps = max(0.05, n / max(duration_s, 0.1))
    try:
        p = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-i", str(video),
             "-vf", f"fps={fps:.4f},scale={width}:{height}",
             "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("자막 위치 분석용 프레임을 못 받았어요: %s", str(e)[:120])
        return []
    buf, size = p.stdout, width * height
    return [buf[i * size:(i + 1) * size] for i in range(len(buf) // size)]


def _row_scores(frames: List[bytes], width: int, height: int) -> List[int]:
    """가로줄마다 «글자 가장자리» 점수 — 밝기만 보면 밝은 배경에서 자막이 묻힌다."""
    scores = []
    for y in range(height):
        s = 0
        base = y * width
        for fr in frames:
            row = fr[base:base + width]
            prev = row[0] if row else 0
            for v in row[1:]:
                if abs(v - prev) > EDGE_STEP:
                    s += 1
                prev = v
        scores.append(s)
    return scores


def find_subtitle_band(video: str, *, search_from: float = SEARCH_FROM
                       ) -> Optional[Tuple[int, int]]:
    """원본에 박힌 자막이 있는 세로 범위 (y0, y1) — 못 찾으면 None.

    좌표는 **원본 영상 크기 기준**이다 (화면을 줄이기 전에 가려야 하므로).
    """
    src_w, src_h = ff.probe_video_size(video)
    if not src_w or not src_h:
        return None
    dur_s = max(0.2, ff.probe_duration_us(video) / 1e6)
    w = min(PROBE_WIDTH, src_w)
    h = max(2, int(src_h * w / src_w)) & ~1
    frames = _gray_frames(video, w, h, PROBE_FRAMES, dur_s)
    if len(frames) < 2:
        return None
    scores = _row_scores(frames, w, h)
    lo = min(h - 1, max(0, int(h * search_from)))
    peak = max(scores[lo:], default=0)
    if peak < MIN_PEAK:
        return None                      # 자막이 없거나 너무 옅다 — 손대지 않는다
    rows = [y for y in range(lo, h) if scores[y] > peak * PEAK_RATIO]
    if not rows:
        return None
    y0 = int(min(rows) * src_h / h)
    y1 = int((max(rows) + 1) * src_h / h)
    y0 = max(0, y0 - PAD_PX)
    y1 = min(src_h, y1 + PAD_PX)
    if y1 - y0 < 4:
        return None
    return (y0, y1)


def clamp_band(band: Tuple[int, int], src_w: int, src_h: int
               ) -> Optional[Tuple[int, int, int, int]]:
    """(y0, y1) → delogo가 받아들이는 (x, y, w, h).

    ⚠ delogo는 **가리는 칸 바깥 화소에서 색을 끌어와** 메운다. 그래서 화면 끝에
    딱 붙으면 «Logo area is outside of the frame»으로 **실패한다**(실측).
    사방 1px을 남긴다 — 자막은 가운데 정렬이라 실무상 문제가 없다.
    """
    y0, y1 = int(band[0]), int(band[1])
    y0 = max(1, min(y0, src_h - 3))
    y1 = max(y0 + 2, min(y1, src_h - 1))
    x, w = 1, max(2, src_w - 2)
    h = y1 - y0
    if h < 2 or w < 2:
        return None
    return (x, y0, w, h)


def delogo_filter(band: Tuple[int, int], src_w: int, src_h: int) -> str:
    """자막을 가리는 FFmpeg 필터 문자열 (못 만들면 빈 문자열)."""
    box = clamp_band(band, src_w, src_h)
    if not box:
        return ""
    x, y, w, h = box
    return f"delogo=x={x}:y={y}:w={w}:h={h}"


def resolve_band(video: str, mode: str = "auto",
                 manual: Optional[Tuple[int, int]] = None
                 ) -> Tuple[Optional[Tuple[int, int]], str]:
    """쓸 자막 범위와 사람이 읽을 안내 문구.

    mode: "auto"(자동으로 찾기) | "manual"(회원님이 직접 지정)
    """
    src_w, src_h = ff.probe_video_size(video)
    if mode == "manual":
        if not manual:
            return None, "지울 자막 위치를 지정해 주세요"
        y0, y1 = int(manual[0]), int(manual[1])
        if y1 <= y0:
            return None, "자막 위치가 거꾸로예요 (아래쪽 값이 더 커야 해요)"
        return (max(0, y0), min(src_h, y1)), f"직접 지정한 자리를 지웠어요 (y {y0}~{y1})"
    band = find_subtitle_band(video)
    if not band:
        return None, ("원본 자막을 못 찾았어요 — 자막이 없거나 흐릿한 영상이에요. "
                      "직접 지정하면 그 자리를 지울 수 있어요")
    pct = round(band[0] / max(src_h, 1) * 100)
    return band, f"원본 자막을 찾아 지웠어요 (화면 위에서 {pct}% 지점, 높이 {band[1]-band[0]}px)"
