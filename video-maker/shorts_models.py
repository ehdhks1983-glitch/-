"""
shorts_models.py — 쇼츠 데이터 구조
ShortsSegment(장면 1개) / ShortsProject(전체 설정).
(부록 A 분리: 분리 전 shorts_maker.py의 데이터 구조부 — 동작 동일)
"""

from typing import List

try:
    from config import KENBURNS as _KENBURNS
except Exception:
    _KENBURNS = {}

TEMPLATES = ("blur", "fill", "card")


class ShortsSegment:
    """쇼츠 한 장면(사진 1장)"""
    def __init__(self, image_path: str = "", duration: float = 3.0,
                 caption: str = "", narration: str = "", template: str = "blur"):
        self.image_path = image_path
        self.duration = duration       # 최소 노출 시간(초). 나래이션이 길면 자동 연장
        self.caption = caption         # 화면에 보이는 자막
        self.narration = narration     # 음성으로 읽을 글
        self.template = template if template in TEMPLATES else "blur"


class ShortsProject:
    """쇼츠 전체 설정"""
    def __init__(self):
        self.segments: List[ShortsSegment] = []
        self.bgm_path: str = ""        # 배경음악 파일(선택)
        self.bgm_volume: float = 0.18  # 0.0~1.0 (음성 위로 너무 크지 않게)
        self.fps: int = 30
        self.caption_size: int = 56    # 자막 기본 크기(1080 기준)
        self.caption_color: str = "#FFFFFF"
        self.output_path: str = ""
        self.cancelled: bool = False
        # 켄번스 줌/팬 모션 on/off (1-1). 기본값은 config.KENBURNS["enabled"]
        self.kenburns_enabled: bool = bool(_KENBURNS.get("enabled", True))
