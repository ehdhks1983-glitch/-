"""출력 B: Timeline Spec → FFmpeg 직접 렌더 → 완성 mp4 (기획안 §5.5).

    render(spec, workdir) 한 번으로:
      ① audio_assembler: 문장 클립+갭 → voice_full.m4a
      ② ass_writer:      자막 .ass 생성
      ③ (옵션) 하단 그라데이션 PNG 생성
      ④ ffmpeg_composer: 필터그래프 합성 (GPU 자동 감지)
      ⑤ 싱크·품질 자가검증: 총길이 ±50ms, 오디오 스트림 존재, 해상도 일치
         → 실패 시 재시도 1회(CPU 강제) 후 오류 리포트
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from ...spec import TimelineSpec
from ...utils import ffmpeg as ff
from ...utils.png import bottom_gradient_overlay_png
from . import ass_writer, audio_assembler, ffmpeg_composer
from .ffmpeg_composer import RenderOptions

DEFAULT_FONTS_DIR = str(Path(__file__).resolve().parents[3] / "resources" / "fonts")
SYNC_TOLERANCE_US = 50_000  # ±50ms (기획안 §5.5-4)


@dataclass
class RenderResult:
    ok: bool
    out_path: str
    encoder: str = ""
    measured_duration_us: int = 0
    spec_duration_us: int = 0
    width: int = 0
    height: int = 0
    has_audio: bool = False
    attempts: int = 0
    errors: List[str] = field(default_factory=list)


def verify_output(spec: TimelineSpec, out_path: str, tolerance_us: int = SYNC_TOLERANCE_US) -> List[str]:
    """렌더 결과 ffprobe 자가검증 — 문제 목록 반환 (비면 통과)."""
    problems = []
    measured = ff.probe_duration_us(out_path)
    if abs(measured - spec.duration_us) > tolerance_us:
        problems.append(
            f"총길이 오차 초과: 실측 {measured}μs vs 스펙 {spec.duration_us}μs"
        )
    if not ff.has_audio_stream(out_path):
        problems.append("오디오 스트림 없음")
    w, h = ff.probe_video_size(out_path)
    if (w, h) != (spec.canvas.w, spec.canvas.h):
        problems.append(f"해상도 불일치: {w}x{h} != {spec.canvas.w}x{spec.canvas.h}")
    return problems


def render(
    spec: TimelineSpec,
    workdir,
    out_path: Optional[str] = None,
    fonts_dir: str = DEFAULT_FONTS_DIR,
    opts: Optional[RenderOptions] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> RenderResult:
    """Timeline Spec을 mp4로 렌더링. 중간 산출물은 workdir에 보존된다."""
    spec.validate()
    missing = spec.missing_files()
    if missing:
        raise FileNotFoundError(f"spec이 참조하는 파일 없음: {missing}")

    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    out = str(out_path or work / "output.mp4")
    opts = opts or RenderOptions()

    voice = str(work / "voice_full.m4a")
    audio_assembler.assemble(spec, voice)
    if spec.sfx:  # 🔔 효과음을 보이스 트랙 위에 (v0.53 — 실패해도 렌더는 계속)
        from ..sfx import mix_sfx  # noqa: PLC0415

        voice = mix_sfx(voice, spec.sfx, str(work / "voice_sfx.m4a"))

    ass = ass_writer.write_ass(spec, work / "subs.ass")

    gradient = None
    if spec.style.gradient_overlay:
        gradient = bottom_gradient_overlay_png(
            str(work / "gradient.png"), spec.canvas.w, spec.canvas.h
        )

    result = RenderResult(ok=False, out_path=out, spec_duration_us=spec.duration_us)
    for attempt in range(2):  # 자가검증 실패 시 재시도 1회 (2회차는 CPU 강제)
        result.attempts = attempt + 1
        if attempt == 1:
            opts = RenderOptions(
                crf=opts.crf, preset=opts.preset, use_gpu="off",
                audio_bitrate=opts.audio_bitrate,
            )
        result.encoder = ffmpeg_composer.compose(
            spec, voice, ass, out, fonts_dir,
            gradient_path=gradient, opts=opts, progress_cb=progress_cb,
        )
        problems = verify_output(spec, out)
        if not problems:
            result.ok = True
            result.errors = []  # 이전 시도(GPU 등)의 오류는 성공했으니 지움
            break
        result.errors = problems

    result.measured_duration_us = ff.probe_duration_us(out)
    result.width, result.height = ff.probe_video_size(out)
    result.has_audio = ff.has_audio_stream(out)
    return result
