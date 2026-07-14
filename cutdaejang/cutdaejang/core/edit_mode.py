"""내 영상 편집 오케스트레이션 (기획안 v1.5 육성 촬영 모드).

    edit_video(video, workdir, stt, ...):
      ① 무음 감지 → 발화 구간
      ② 발화 구간만 이어붙인 컷 영상(자체 오디오 유지)
      ③ 구간별 오디오 → STT → 자막 텍스트 (타이밍은 ①에서, 글자는 STT에서)
      ④ 컷 영상 + 자동 자막 번인 → mp4 (쇼츠 세로 / 원본 비율)
"""

from __future__ import annotations

import json
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
    hook: str = "",                    # 상단 제목(훅)
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

    # 자막 .ass — ass_writer는 spec.canvas/style/subtitles/hook만 사용
    ass_spec = TimelineSpec(
        canvas=canvas,
        duration_us=dur_us,
        hook=hook,
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


@dataclass
class EditAnalysis:
    """1단계(분석) 결과 — 자막 검토·수정 후 2단계(렌더)로 넘긴다 (Phase 1)."""
    video_path: str
    cut_video: str
    subtitles: List[Subtitle]
    original_us: int
    cut_us: int
    removed_ratio: float
    segments: int
    stt_calls: int = 0
    hallucinations: int = 0
    notes: List[str] = field(default_factory=list)


def subtitles_to_dicts(subs: List[Subtitle]) -> List[dict]:
    return [{"text": s.text, "start_us": s.start_us, "end_us": s.end_us} for s in subs]


def dicts_to_subtitles(dicts: List[dict]) -> List[Subtitle]:
    out = []
    for d in dicts:
        text = (d.get("text") or "").strip()
        if text:  # 빈 자막은 제외
            out.append(Subtitle(text=text, start_us=int(d["start_us"]), end_us=int(d["end_us"])))
    return out


def save_srt(subs: List[Subtitle], path) -> str:
    """자막을 .srt로 저장 (다른 편집기에서도 열 수 있게)."""
    def ts(us: int) -> str:
        ms = us // 1000
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, s in enumerate(subs, 1):
        lines.append(str(i))
        lines.append(f"{ts(s.start_us)} --> {ts(s.end_us)}")
        lines.append(s.text)
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def analyze_video(
    video_path: str,
    workdir,
    stt: Optional[STTEngine],
    auto_subtitle: bool = True,
    cut_silence: bool = True,
    silence_opts: Optional[SilenceOptions] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> EditAnalysis:
    """1단계: 무음컷 + 자동자막 → 검토용 자막 목록 반환 (렌더는 아직 안 함)."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    video_path = video_editor.resolve_input_video(video_path)
    notes: List[str] = []

    def report(stage: str, frac: float) -> None:
        if progress_cb:
            progress_cb(stage, frac)

    def note(msg: str) -> None:
        log.info("%s", msg)
        notes.append(msg)
        if status_cb:
            status_cb(msg)

    report("analyze", 0.0)
    if cut_silence:
        segments, original_us = video_editor.detect_speech_segments(video_path, silence_opts)
    else:
        original_us = ff.probe_duration_us(video_path)
        segments = [(0, original_us)]
    removed = video_editor.silence_ratio(segments, original_us)
    note(
        f"발화 구간 {len(segments)}개 — 무음 약 {removed * 100:.0f}% 컷" if cut_silence
        else "무음컷 없이 원본 길이 유지"
    )

    report("cut", 0.0)
    if not cut_silence:
        cut_path = str(video_path)
    else:
        cut_path = video_editor.cut_and_concat(video_path, segments, str(work / "cut.mp4"))
    cut_us = ff.probe_duration_us(cut_path)

    cut_segments = video_editor.remap_to_cut_timeline(segments)
    subtitles: List[Subtitle] = []
    stt_calls = halluc = 0
    if auto_subtitle and stt is not None:
        report("stt", 0.0)
        texts = transcribe_segments(
            video_path, segments, stt, work,
            on_progress=lambda i, n: report("stt", i / n),
        )
        subtitles = build_subtitles(cut_segments, texts)
        stt_calls = stt.stats["calls"]
        halluc = stt.stats.get("hallucinations", 0)
        if not subtitles:
            note("말소리가 감지되지 않아 자막이 없습니다"
                 + (f" (음악/잡음 오인 {halluc}건 제거)" if halluc else ""))
        elif halluc:
            note(f"음악/잡음 오인 자막 {halluc}건 제거")

    # 검토·재편집용 저장
    (work / "subtitles.json").write_text(
        json.dumps(subtitles_to_dicts(subtitles), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if subtitles:
        save_srt(subtitles, work / "subtitles.srt")

    return EditAnalysis(
        video_path=str(video_path), cut_video=cut_path, subtitles=subtitles,
        original_us=original_us, cut_us=cut_us, removed_ratio=removed,
        segments=len(segments), stt_calls=stt_calls, hallucinations=halluc, notes=notes,
    )


def render_from_analysis(
    cut_video: str,
    subtitles: List[Subtitle],
    out_path: str,
    style: Optional[Style] = None,
    layout: str = "shorts",
    hook: str = "",
    opts: Optional[RenderOptions] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> EditResult:
    """2단계: (수정된) 자막으로 최종 렌더."""
    style = style or presets.SUBTITLE_STYLE_PRESETS["shorts_basic"]
    result = EditResult(ok=False, out_path=out_path)
    result.cut_us = ff.probe_duration_us(cut_video)
    result.subtitles = [s.text for s in subtitles]
    try:
        # 저장된 .srt 갱신 (사용자 수정 반영)
        if subtitles:
            save_srt(subtitles, Path(out_path).parent / "subtitles.srt")
        render_edited(
            cut_video, subtitles, out_path, style, layout=layout, hook=hook, opts=opts,
            progress_cb=progress_cb,
        )
        if not _fits_us(ff.probe_duration_us(out_path), result.cut_us):
            result.errors.append("출력 길이가 컷 영상과 다릅니다")
        if not ff.has_audio_stream(out_path):
            result.errors.append("출력에 오디오가 없습니다")
        result.ok = not result.errors
    except Exception as e:
        log.exception("편집 렌더 실패")
        result.errors.append(str(e))
    return result


def edit_video(
    video_path: str,
    workdir,
    stt: Optional[STTEngine],
    style: Optional[Style] = None,
    layout: str = "shorts",
    hook: str = "",
    auto_subtitle: bool = True,
    cut_silence: bool = True,
    silence_opts: Optional[SilenceOptions] = None,
    opts: Optional[RenderOptions] = None,
    out_path: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> EditResult:
    """분석+렌더 한 번에 (CLI·자동용). 검토 없이 자동 자막 그대로 렌더."""
    work = Path(workdir)
    out = str(out_path or work / "edited.mp4")
    try:
        analysis = analyze_video(
            video_path, work, stt, auto_subtitle=auto_subtitle, cut_silence=cut_silence,
            silence_opts=silence_opts, progress_cb=progress_cb, status_cb=status_cb,
        )
    except Exception as e:
        log.exception("편집 분석 실패")
        r = EditResult(ok=False, out_path=out)
        r.errors.append(str(e))
        return r
    if progress_cb:
        progress_cb("render", 0.0)
    result = render_from_analysis(
        analysis.cut_video, analysis.subtitles, out, style=style, layout=layout,
        hook=hook, opts=opts,
        progress_cb=lambda f: progress_cb("render", f) if progress_cb else None,
    )
    result.original_us = analysis.original_us
    result.removed_ratio = analysis.removed_ratio
    result.segments = analysis.segments
    result.stt_calls = analysis.stt_calls
    return result
