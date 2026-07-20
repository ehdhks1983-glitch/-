"""Timeline Spec (IR) — 렌더 경로(render_engine)의 단일 진실 원천.

기획안 §3.2의 JSON 형태를 그대로 직렬화/역직렬화한다. 모든 시간은 μs 정수.
검증·직렬화 후 jobs 테이블에 저장되어 "재생성" 시 어느 출력으로든 재빌드 가능해야 한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


class SpecError(ValueError):
    """Timeline Spec 검증 실패."""


def _require_int_us(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpecError(f"{name}은(는) μs 정수여야 합니다: {value!r}")
    return value


@dataclass
class Canvas:
    w: int = 1080
    h: int = 1920
    fps: int = 30


@dataclass
class Background:
    type: str = "image"  # "image" | "color" | "video"(장면별 이미지 슬라이드, v0.45)
    path: Optional[str] = None
    color: Optional[str] = None  # 예: "#101020" (type=color일 때)
    motion: str = "off"          # Ken Burns: "zoom_in" | "zoom_out" | "off" (image 전용)
    motion_amount: float = 0.08  # 총 줌 비율


@dataclass
class MainVideo:
    path: str = ""
    layout: str = "top"        # "top" | "center" | "full"
    scale: float = 0.9
    fit: str = "trim"          # 영상이 spec보다 길 때: 잘라냄
    short_policy: str = "freeze_last"  # 짧을 때: "freeze_last" | "loop"


@dataclass
class AudioClip:
    path: str
    start_us: int
    end_us: int


@dataclass
class Subtitle:
    text: str
    start_us: int
    end_us: int
    highlight: str = ""  # 문장 내 강조 단어 (없으면 빈 문자열)


@dataclass
class Bgm:
    path: str = ""
    volume_db: float = -20.0
    duck: bool = False  # 음성 구간 자동 덕킹(sidechaincompress)


@dataclass
class Style:
    font: str = "Pretendard-ExtraBold"
    size: int = 64
    outline: int = 3
    shadow: int = 0
    position: str = "bottom"   # "bottom" | "center" | "top"
    gradient_overlay: bool = True
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    margin_v: Optional[int] = None  # 지정 시 position 프리셋의 세로 여백을 덮어씀
    fade: bool = False              # 자막 등장/퇴장 페이드 {\fad(100,60)}
    highlight_color: str = "#FFD400"
    band: bool = False             # 자막 뒤 배경 띠 (유튜브 썸네일 스타일)
    hook_band: bool = True         # 상단 제목 뒤 배경 띠 (기본 켬)
    wrap_chars: int = 16           # 자막 한 줄 최대 글자수(넘으면 2줄로 자동 줄바꿈). 0=끔
    hook_scale: float = 1.0        # 상단 제목 크기 배수 (0.6~1.6, UI 크기 선택)
    anim: str = "none"             # 자막 등장 애니메이션: none | pop (살짝 커지며 등장)
    hook_style: str = "기본"        # 상단 제목 스타일 프리셋 (v0.52) — ass_writer.HOOK_STYLES 키
    sub_style: str = "기본"         # 본문 자막 스타일 프리셋 (v0.54) — ass_writer.SUB_STYLES 키


@dataclass
class Punch:
    """펀치인 줌 구간 (v0.55) — 이 구간에서 화면이 살짝 확대됐다 복귀."""

    start_us: int = 0
    end_us: int = 0


@dataclass
class Sfx:
    """효과음 이벤트 (v0.53) — 보이스 트랙 위에 start_us 시점으로 얹는다."""

    path: str = ""
    start_us: int = 0
    gain_db: float = -13.0
    name: str = ""      # pop | whoosh | ding (표시·디버깅용)


@dataclass
class TimelineSpec:
    mode: str = "shorts"
    canvas: Canvas = field(default_factory=Canvas)
    duration_us: int = 0
    hook: str = ""  # 상단에 계속 표시되는 큰 제목(훅). 줄바꿈은 \n
    background: Background = field(default_factory=Background)
    main_video: Optional[MainVideo] = None
    bgm: Optional[Bgm] = None
    audio: List[AudioClip] = field(default_factory=list)
    subtitles: List[Subtitle] = field(default_factory=list)
    style: Style = field(default_factory=Style)
    sfx: List[Sfx] = field(default_factory=list)  # 효과음 (v0.53) — 없으면 빈 목록
    punchins: List[Punch] = field(default_factory=list)  # 펀치인 줌 (v0.55)

    # ---------- 직렬화 ----------

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.main_video is None:
            d.pop("main_video")
        if self.bgm is None:
            d.pop("bgm")
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, d: dict) -> "TimelineSpec":
        def pick(dc, src):
            fields = {f for f in dc.__dataclass_fields__}  # 알 수 없는 키는 무시 (전방 호환)
            return dc(**{k: v for k, v in (src or {}).items() if k in fields})

        return cls(
            mode=d.get("mode", "shorts"),
            canvas=pick(Canvas, d.get("canvas")),
            duration_us=d.get("duration_us", 0),
            hook=d.get("hook", ""),
            background=pick(Background, d.get("background")),
            main_video=pick(MainVideo, d["main_video"]) if d.get("main_video") else None,
            bgm=pick(Bgm, d["bgm"]) if d.get("bgm") else None,
            audio=[pick(AudioClip, a) for a in d.get("audio", [])],
            subtitles=[pick(Subtitle, s) for s in d.get("subtitles", [])],
            style=pick(Style, d.get("style")),
            sfx=[pick(Sfx, s) for s in d.get("sfx", [])],
            punchins=[pick(Punch, s) for s in d.get("punchins", [])],
        )

    @classmethod
    def from_json(cls, text: str) -> "TimelineSpec":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path) -> "TimelineSpec":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    # ---------- 검증 ----------

    def validate(self) -> "TimelineSpec":
        if self.mode not in ("shorts", "landscape"):
            raise SpecError(f"지원하지 않는 mode: {self.mode}")
        if self.canvas.w <= 0 or self.canvas.h <= 0 or self.canvas.fps <= 0:
            raise SpecError(f"canvas 값 오류: {self.canvas}")
        _require_int_us("duration_us", self.duration_us)
        if self.duration_us <= 0:
            raise SpecError("duration_us는 0보다 커야 합니다")

        if self.background.type in ("image", "video"):
            if not self.background.path:
                raise SpecError(f"background.type={self.background.type}에는 path가 필요합니다")
        elif self.background.type == "color":
            if not self.background.color:
                raise SpecError("background.type=color에는 color가 필요합니다")
        else:
            raise SpecError(f"지원하지 않는 background.type: {self.background.type}")
        if self.background.motion not in ("zoom_in", "zoom_out", "off"):
            raise SpecError(f"지원하지 않는 background.motion: {self.background.motion}")

        if self.bgm is not None and not self.bgm.path:
            raise SpecError("bgm에는 path가 필요합니다")

        if self.main_video is not None:
            mv = self.main_video
            if not mv.path:
                raise SpecError("main_video.path가 비어 있습니다")
            if mv.layout not in ("top", "center", "full"):
                raise SpecError(f"지원하지 않는 layout: {mv.layout}")
            if not (0.1 <= mv.scale <= 1.0):
                raise SpecError(f"main_video.scale 범위(0.1~1.0) 밖: {mv.scale}")
            if mv.short_policy not in ("freeze_last", "loop"):
                raise SpecError(f"지원하지 않는 short_policy: {mv.short_policy}")

        for name, clips in (("audio", self.audio), ("subtitles", self.subtitles)):
            prev_end = None
            for i, c in enumerate(clips):
                start = _require_int_us(f"{name}[{i}].start_us", c.start_us)
                end = _require_int_us(f"{name}[{i}].end_us", c.end_us)
                if start < 0 or end <= start:
                    raise SpecError(f"{name}[{i}] 구간 오류: {start}~{end}")
                if end > self.duration_us:
                    raise SpecError(
                        f"{name}[{i}] 종료({end})가 duration_us({self.duration_us})를 초과"
                    )
                if prev_end is not None and start < prev_end:
                    raise SpecError(f"{name}[{i}]가 이전 클립과 겹칩니다 ({start} < {prev_end})")
                prev_end = end

        if self.style.size <= 0 or self.style.outline < 0:
            raise SpecError(f"style 값 오류: size={self.style.size}, outline={self.style.outline}")
        if self.style.position not in ("bottom", "center", "top"):
            raise SpecError(f"지원하지 않는 style.position: {self.style.position}")
        return self

    # ---------- 경로 ----------

    def missing_files(self, base_dir: Optional[str] = None) -> List[str]:
        """존재하지 않는 참조 파일 목록 (상대 경로는 base_dir 기준)."""
        base = Path(base_dir) if base_dir else Path(".")

        def ok(p: str) -> bool:
            path = Path(p)
            return (path if path.is_absolute() else base / path).exists()

        missing = []
        if (self.background.type in ("image", "video") and self.background.path
                and not ok(self.background.path)):
            missing.append(self.background.path)
        if self.main_video and not ok(self.main_video.path):
            missing.append(self.main_video.path)
        if self.bgm and not ok(self.bgm.path):
            missing.append(self.bgm.path)
        missing += [a.path for a in self.audio if not ok(a.path)]
        return missing

    def resolve_paths(self, base_dir: str) -> "TimelineSpec":
        """상대 경로를 base_dir 기준 절대 경로로 치환한 새 spec 반환."""
        base = Path(base_dir)

        def absolutize(p: Optional[str]) -> Optional[str]:
            if not p:
                return p
            path = Path(p)
            return str(path if path.is_absolute() else (base / path).resolve())

        spec = TimelineSpec.from_dict(self.to_dict())
        spec.background.path = absolutize(spec.background.path)
        if spec.main_video:
            spec.main_video.path = absolutize(spec.main_video.path)
        if spec.bgm:
            spec.bgm.path = absolutize(spec.bgm.path)
        for a in spec.audio:
            a.path = absolutize(a.path)
        return spec
