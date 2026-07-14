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


def align_script_to_segments(
    lines: List[str], cut_segments: List[tuple], total_us: Optional[int] = None
) -> List[Subtitle]:
    """사용자가 미리 가진 대본 줄들을 컷 타임라인에 배치 (STT 대신).

    - 줄 수 == 발화 구간 수: 1:1 매핑 → 사용자 텍스트가 실제 발화 타이밍에 정확히 얹힘
    - 그 외(무내레이션 b-roll·구간 수 불일치): 컷 전체 길이를 글자 수에 비례해 분배
    STT 오인식·비용 없이 정확한 자막을 얻는 경로. 이후 검토 화면에서 타이밍 미세조정 가능.
    """
    clean = [ln.strip() for ln in lines if ln.strip()]
    if not clean:
        return []
    if cut_segments and len(clean) == len(cut_segments):
        return [Subtitle(text=t, start_us=int(s), end_us=int(e))
                for t, (s, e) in zip(clean, cut_segments)]
    start = int(cut_segments[0][0]) if cut_segments else 0
    end = int(cut_segments[-1][1]) if cut_segments else int(total_us or 0)
    span = max(end - start, len(clean) * 900_000)  # 최소 줄당 0.9초 확보
    weights = [max(len(t), 1) for t in clean]
    total_w = sum(weights)
    subs, cursor = [], start
    for i, (t, w) in enumerate(zip(clean, weights)):
        dur = int(span * w / total_w)
        e = end if i == len(clean) - 1 else cursor + dur
        subs.append(Subtitle(text=t, start_us=cursor, end_us=max(e, cursor + 300_000)))
        cursor += dur
    return subs


def _atempo_chain(speed: float) -> str:
    """atempo는 0.5~2.0만 지원 → 범위 밖이면 여러 개로 나눠 곱한다."""
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0"); s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5"); s /= 0.5
    parts.append(f"atempo={s:.6f}")
    return ",".join(parts)


def render_edited(
    cut_video: str,
    subtitles: List[Subtitle],
    out_path: str,
    style: Style,
    layout: str = "shorts",            # "shorts"(세로 1080x1920) | "keep"(원본 비율)
    hook: str = "",                    # 상단 제목(훅)
    fonts_dir: str = DEFAULT_FONTS_DIR,
    opts: Optional[RenderOptions] = None,
    speed: float = 1.0,                # 저장(렌더) 속도 배수 (1.25/1.5/2배 등)
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """컷 영상에 자동 자막을 번인. 영상 자체 오디오를 유지한다.

    speed>1이면 자막을 구운 뒤 영상·오디오를 통째로 배속 → 자막이 그대로 싱크 유지.
    """
    opts = opts or RenderOptions()
    speed = max(0.25, min(4.0, float(speed or 1.0)))
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
            f"[comp]{subs_arg}[vc]"
        )
    else:
        vf = f"[0:v]scale={canvas.w}:{canvas.h},{subs_arg}[vc]"

    slow = abs(speed - 1.0) > 1e-3
    if slow:  # 자막 구운 뒤 통째로 배속 (영상·오디오 함께 → 싱크 유지)
        vf += f";[vc]setpts=PTS/{speed:.6f}[v];[0:a]{_atempo_chain(speed)}[a]"
        vmap, amap = "[v]", "[a]"
        out_us = int(dur_us / speed)
    else:
        vmap, amap = "[vc]", "0:a"
        out_us = dur_us

    args = [
        "-y", "-i", str(cut_video),
        "-filter_complex", vf,
        "-map", vmap, "-map", amap,
        "-c:v", "libx264", "-crf", str(opts.crf), "-preset", opts.preset,
        "-pix_fmt", "yuv420p", "-r", str(canvas.fps),
        "-c:a", "aac", "-b:a", opts.audio_bitrate, "-movflags", "+faststart",
        str(out_path),
    ]
    ff.run_with_progress(args, total_us=out_us, progress_cb=progress_cb)
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
    return [
        {"text": s.text, "start_us": s.start_us, "end_us": s.end_us, "highlight": s.highlight}
        for s in subs
    ]


def split_highlight(text: str) -> tuple:
    """``문장 | 강조단어`` → (문장, 강조단어). 세로줄(|)은 항상 구분자로 취급.

    AI 모드와 동일한 관례. 강조단어가 문장에 실제로 들어있어야 렌더 때 색이 입혀진다.
    """
    if "|" in text:
        head, _, tail = text.rpartition("|")
        return head.strip(), tail.strip()
    return text.strip(), ""


def dicts_to_subtitles(dicts: List[dict]) -> List[Subtitle]:
    out = []
    for d in dicts:
        text, hl = split_highlight((d.get("text") or "").strip())
        hl = (d.get("highlight") or hl or "").strip()
        if text:  # 빈 자막은 제외
            out.append(Subtitle(
                text=text, start_us=int(d["start_us"]), end_us=int(d["end_us"]), highlight=hl,
            ))
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
    script_lines: Optional[List[str]] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> EditAnalysis:
    """1단계: 무음컷 + 자동자막 → 검토용 자막 목록 반환 (렌더는 아직 안 함).

    script_lines가 있으면 STT 대신 사용자 대본을 컷 타임라인에 배치한다
    (오인식·비용 없음). 없으면 기존대로 STT로 자동 자막을 만든다.
    """
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
    clean_script = [ln.strip() for ln in (script_lines or []) if ln.strip()]
    if clean_script:
        # 사용자 대본 우선 — STT 건너뛰고 대본을 컷 타임라인에 배치
        subtitles = align_script_to_segments(clean_script, cut_segments, total_us=cut_us)
        note(f"입력한 대본 {len(subtitles)}줄을 영상 타이밍에 배치했습니다 (음성 인식 생략)")
    elif auto_subtitle and stt is not None:
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


def _remap_subs_to_ranges(kept: List[Subtitle], ranges: List[tuple]) -> List[Subtitle]:
    """고른 자막들을 잘라 이어붙인 새 타임라인(0부터)으로 재매핑."""
    new_start, cursor = [], 0
    for a, b in ranges:
        new_start.append(cursor)
        cursor += (b - a)
    out: List[Subtitle] = []
    for s in kept:
        for (a, b), ns in zip(ranges, new_start):
            if a <= s.start_us < b:
                out.append(Subtitle(
                    text=s.text, highlight=s.highlight,
                    start_us=ns + (s.start_us - a),
                    end_us=ns + (min(s.end_us, b) - a),
                ))
                break
    return out


def rebuild_from_keep(
    cut_video: str, subtitles: List[Subtitle], keep_idx: List[int], out_path: str,
    pad_us: int = 150_000,
) -> tuple:
    """검토화면에서 고른 자막(keep_idx)만 남겨 컷 영상을 다시 자른다 → 진짜 쇼츠 길이.

    각 자막 구간을 앞뒤로 살짝(pad) 넉넉히 잡아 말이 잘리지 않게 하고, 인접/겹치는
    구간은 병합한다. 자막은 새 타임라인으로 재매핑해 반환. (핵심만 짧고 굵게)
    """
    kept = [subtitles[i] for i in keep_idx if 0 <= i < len(subtitles)]
    if not kept:
        raise ValueError("남길 자막을 하나 이상 선택하세요")
    dur = ff.probe_duration_us(cut_video)
    ranges: List[tuple] = []
    for s in sorted(kept, key=lambda x: x.start_us):
        a, b = max(0, s.start_us - pad_us), min(dur, s.end_us + pad_us)
        if ranges and a <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], b))
        else:
            ranges.append((a, b))
    new_video = video_editor.cut_and_concat(cut_video, ranges, out_path)
    return new_video, _remap_subs_to_ranges(sorted(kept, key=lambda x: x.start_us), ranges)


def render_from_analysis(
    cut_video: str,
    subtitles: List[Subtitle],
    out_path: str,
    style: Optional[Style] = None,
    layout: str = "shorts",
    hook: str = "",
    opts: Optional[RenderOptions] = None,
    speed: float = 1.0,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> EditResult:
    """2단계: (수정된) 자막으로 최종 렌더. speed>1이면 저장 영상도 배속."""
    style = style or presets.SUBTITLE_STYLE_PRESETS["shorts_basic"]
    speed = max(0.25, min(4.0, float(speed or 1.0)))
    result = EditResult(ok=False, out_path=out_path)
    result.cut_us = ff.probe_duration_us(cut_video)
    result.subtitles = [s.text for s in subtitles]
    try:
        # 저장된 .srt 갱신 (사용자 수정 반영)
        if subtitles:
            save_srt(subtitles, Path(out_path).parent / "subtitles.srt")
        render_edited(
            cut_video, subtitles, out_path, style, layout=layout, hook=hook, opts=opts,
            speed=speed, progress_cb=progress_cb,
        )
        if not _fits_us(ff.probe_duration_us(out_path), int(result.cut_us / speed), tol=200_000):
            result.errors.append("출력 길이가 예상과 다릅니다")
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
    script_lines: Optional[List[str]] = None,
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
            script_lines=script_lines,
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
