"""컷대장 — 유튜브 쇼츠·영상 자동 제작 (주제→대본→TTS→배경→자막→mp4).

Timeline Spec(IR) → render_engine(FFmpeg) → mp4 로 무인 대량생산한다.
(CapCut draft 출력은 v0.41에서 제거 — mp4 전용)
"""

__version__ = "0.72.0"

from .spec import TimelineSpec  # noqa: F401
