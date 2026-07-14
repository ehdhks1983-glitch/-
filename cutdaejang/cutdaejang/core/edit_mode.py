"""내 영상 편집 오케스트레이션 (기획안 v1.5 육성 촬영 모드).

    edit_video(video, workdir, stt, ...):
      ① 무음 감지 → 발화 구간
      ② 발화 구간만 이어붙인 컷 영상(자체 오디오 유지)
      ③ 구간별 오디오 → STT → 자막 텍스트 (타이밍은 ①에서, 글자는 STT에서)
      ④ 컷 영상 + 자동 자막 번인 → mp4 (쇼츠 세로 / 원본 비율)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .. import presets
from ..spec import Background, Canvas, Style, Subtitle, TimelineSpec
from ..utils import ffmpeg as ff
from . import video_editor
from .render_engine import DEFAULT_FONTS_DIR, ass_writer
from .render_engine.ffmpeg_composer import RenderOptions
from .stt_engine import STTEngine
from .video_editor import SilenceOptions

log = logging.getLogger("cutdaejang")


@dataclass
class EditResult:
    ok: bool
    out_path: str
    original_us: int = 0
    cut_us: int = 0
    removed_ratio: float = 0.0
    segments: int = 0
    subtitles: List[str] = field(default_factory=list)
    stt_calls: int = 0
    errors: List[str] = field(default_factory=list)


def _fits_us(a: int, b: int, tol: int = 120_000) -> bool:
    return abs(a - b) <= tol


def transcribe_segments(
    video_path: str,
    segments: List[tuple],
    stt: STTEngine,
    workdir: Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[str]:
    """각 발화 구간 오디오를 추출해 STT. 구간과 1:1 대응하는 텍스트 리스트."""
    texts: List[str] = []
    seg_dir = workdir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    for i, (s, e) in enumerate(segments):
        wav = seg_dir / f"seg{i:03d}.wav"
        video_editor.extract_segment_audio(video_path, s, e, str(wav))
        try:
            texts.append(stt.transcribe(str(wav)).strip())
        except Exception as ex:  # 한 구간 실패는 빈 자막으로 (영상은 살림)
            log.warning("구간 %d STT 실패: %s", i, ex)
            texts.append("")
        if on_progress:
            on_progress(i + 1, len(segments))
    return texts


def build_subtitles(cut_segments: List[tuple], texts: List[str]) -> List[Subtitle]:
    """컷 타임라인 구간 + 텍스트 → 자막 (빈 텍스트 구간은 자막 생략)."""
    subs = []
    for (s, e), text in zip(cut_segments, texts):
        if text:
            subs.append(Subtitle(text=text, start_us=s, end_us=e))
    return subs


def render_edited(
    cut_video: str,
    subtitles: List[Subtitle],
    out_path: str,
    style: Style,
    layout: str = "shorts",            # "shorts"(세로 1080x1920) | "keep"(원본 비율)
    fonts_dir: str = DEFAULT_FONTS_DIR,
    opts: Optional[RenderOptions] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """컷 영상에 자동 자막을 번인. 영상 자체 오디오를 유지한다."""
    opts = opts or RenderOptions()
    src_w, src_h = ff.probe_video_size(cut_video)
    dur_us = ff.probe_duration_us(cut_video)

    if layout == "shorts":
        canvas = Canvas(w=1080, h=1920, fps=30)
    else:  # keep: 원본 해상도(짝수 보정)
        canvas = Canvas(w=src_w - (src_w % 2), h=src_h - (src_h % 2), fps=30)

    # 자막 .ass — ass_writer는 spec.canvas/style/subtitles만 사용
    ass_spec = TimelineSpec(
        canvas=canvas,
        duration_us=dur_us,
        background=Background(type="color", color="#000000"),
        subtitles=subtitles,
        style=style,
    )
    work = Path(out_path).parent
    ass_path = ass_writer.write_ass(ass_spec, work / "subs.ass")

    subs_arg = (
        f"subtitles=filename={ff.escape_filter_value(str(ass_path))}"
        f":fontsdir={ff.escape_filter_value(str(fonts_dir))}"
    )
    if layout == "shorts":
        # 블러 커버 배경 + 원본 비율 유지 전경 오버레이 (가로영상도 세로로 자연스럽게)
        vf = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={canvas.w}:{canvas.h}:force_original_aspect_ratio=increase,"
            f"crop={canvas.w}:{canvas.h},boxblur=24:2,eq=brightness=-0.1[bgb];"
            f"[fg]scale={canvas.w}:{canvas.h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[comp];"
            f"[comp]{subs_arg}[v]"
        )
    else:
        vf = f"[0:v]scale={canvas.w}:{canvas.h},{subs_arg}[v]"

    args = [
        "-y", "-i", str(cut_video),
        "-filter_complex", vf,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-crf", str(opts.crf), "-preset", opts.preset,
        "-pix_fmt", "yuv420p", "-r", str(canvas.fps),
        "-c:a", "aac", "-b:a", opts.audio_bitrate, "-movflags", "+faststart",
        str(out_path),
    ]
    ff.run_with_progress(args, total_us=dur_us, progress_cb=progress_cb)
    return str(out_path)


def edit_video(
    video_path: str,
    workdir,
    stt: STTEngine,
    style: Optional[Style] = None,
    layout: str = "shorts",
    silence_opts: Optional[SilenceOptions] = None,
    opts: Optional[RenderOptions] = None,
    out_path: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> EditResult:
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    style = style or presets.SUBTITLE_STYLE_PRESETS["shorts_basic"]
    out = str(out_path or work / "edited.mp4")

    def report(stage: str, frac: float) -> None:
        if progress_cb:
            progress_cb(stage, frac)

    def note(msg: str) -> None:
        log.info("%s", msg)
        if status_cb:
            status_cb(msg)

    result = EditResult(ok=False, out_path=out)
    try:
        # ① 무음 감지 → 발화 구간
        report("analyze", 0.0)
        segments, original_us = video_editor.detect_speech_segments(video_path, silence_opts)
        result.original_us = original_us
        result.segments = len(segments)
        result.removed_ratio = video_editor.silence_ratio(segments, original_us)
        note(
            f"발화 구간 {len(segments)}개 감지 — 무음 약 {result.removed_ratio * 100:.0f}% 컷 예정"
        )

        # ② 컷 영상
        report("cut", 0.0)
        cut_path = video_editor.cut_and_concat(video_path, segments, str(work / "cut.mp4"))
        result.cut_us = ff.probe_duration_us(cut_path)

        # ③ 구간별 STT (타이밍은 컷 타임라인으로 remap)
        report("stt", 0.0)
        texts = transcribe_segments(
            video_path, segments, stt, work,
            on_progress=lambda i, n: report("stt", i / n),
        )
        cut_segments = video_editor.remap_to_cut_timeline(segments)
        subtitles = build_subtitles(cut_segments, texts)
        result.subtitles = [s.text for s in subtitles]
        result.stt_calls = stt.stats["calls"]

        # ④ 렌더 (자막 번인)
        report("render", 0.0)
        render_edited(
            cut_path, subtitles, out, style, layout=layout, opts=opts,
            progress_cb=lambda f: report("render", f),
        )

        # 자가검증: 길이·오디오
        if not _fits_us(ff.probe_duration_us(out), result.cut_us):
            result.errors.append("출력 길이가 컷 영상과 다릅니다")
        if not ff.has_audio_stream(out):
            result.errors.append("출력에 오디오가 없습니다")
        result.ok = not result.errors
        note("편집 완료" if result.ok else "완료(경고 있음)")
    except Exception as e:
        log.exception("편집 실패")
        result.errors.append(str(e))
    return result
