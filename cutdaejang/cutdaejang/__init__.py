"""컷대장 — CapCut 쇼츠·영상 조립 자동화 (개발기획안 v1.2 기반).

이중 출력 구조:
  - 출력 A: Timeline Spec → draft_builder → CapCut draft (검수·수정용)
  - 출력 B: Timeline Spec → render_engine(FFmpeg) → mp4 (무인 대량생산용)
"""

__version__ = "0.1.0"

from .spec import TimelineSpec  # noqa: F401
