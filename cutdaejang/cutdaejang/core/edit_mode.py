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
from .render_engine.ffmpeg_composer import _NVENC_PRESETS, RenderOptions
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


def transcribe_segments_timed(
    video_path: str,
    segments: List[tuple],
    stt: STTEngine,
    workdir: Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[list]:
    """각 발화 구간을 문장 단위 타임스탬프로 전사 (v0.41 — whisper).

    반환: 구간과 1:1 대응하는 [(구간 내 상대 시작μs, 끝μs, 텍스트), ...] 리스트.
    제공자가 타임스탬프를 지원하지 않으면 기존 전사로 폴백해 구간 전체를 한 조각으로.
    """
    out: List[list] = []
    seg_dir = workdir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    for i, (s, e) in enumerate(segments):
        wav = seg_dir / f"seg{i:03d}.wav"
        video_editor.extract_segment_audio(video_path, s, e, str(wav))
        pieces: list = []
        try:
            timed = stt.transcribe_timed(str(wav))
            if timed is None:  # 타임스탬프 미지원 제공자(gemini 등) → 구간=한 조각
                text = stt.transcribe(str(wav)).strip()
                timed = [(0, e - s, text)] if text else []
            pieces = timed
        except Exception as ex:  # 한 구간 실패는 빈 자막으로 (영상은 살림)
            log.warning("구간 %d STT 실패: %s", i, ex)
        out.append(pieces)
        if on_progress:
            on_progress(i + 1, len(segments))
    return out


def build_subtitles_timed(
    cut_segments: List[tuple], pieces_per_segment: List[list],
    min_piece_us: int = 200_000,
) -> List[Subtitle]:
    """구간별 문장 조각 → 컷 타임라인 절대 시각 자막 (v0.41).

    조각 시각은 구간 내 상대값 → 컷 구간 시작에 더해 절대화하고 구간 밖은 잘라낸다.
    너무 짧은 조각(기본 0.2초 미만)은 표시 의미가 없어 버린다.
    """
    subs: List[Subtitle] = []
    for (s, e), pieces in zip(cut_segments, pieces_per_segment):
        seg_len = e - s
        for piece in sorted(pieces or []):
            rel_start, rel_end, text = piece[0], piece[1], piece[2]
            p_words = piece[3] if len(piece) > 3 else []   # 단어 시각 (v0.76)
            conf = float(piece[4]) if len(piece) > 4 else 1.0
            a = max(0, min(int(rel_start), seg_len))
            b = max(0, min(int(rel_end), seg_len))
            if not str(text).strip() or (b - a) < min_piece_us:
                continue
            # 단어 시각을 '자막 시작 기준 상대값'으로 — 이후 재컷·시프트에도 그대로 유효
            words = []
            for wa, wb, wt in p_words:
                ra, rb = int(wa) - a, int(wb) - a
                if rb > max(ra, 0) and ra < (b - a):
                    words.append([max(0, ra), min(rb, b - a), str(wt)])
            subs.append(Subtitle(text=str(text).strip(), start_us=s + a, end_us=s + b,
                                 words=words, conf=round(conf, 3)))
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


# 화질(선명도) 프리셋 — 유튜브는 고해상도 업로드에 더 좋은 코덱·비트레이트를 줘 체감 화질↑
#  mult: 기준 해상도 배수(2.0=4K), crf: 낮을수록 고화질, sharpen: 선명화(unsharp)
QUALITY_PRESETS = {
    "draft":    {"mult": 1.0, "crf": 23, "preset": "ultrafast", "sharpen": False},  # 초안·미리보기
    "standard": {"mult": 1.0, "crf": 20, "preset": "fast", "sharpen": False},
    "high":     {"mult": 1.0, "crf": 17, "preset": "medium", "sharpen": "unsharp"},
    # 4K 업스케일: 저압축(crf16) + CAS 적응형 선명화 — 업스케일 물러짐 보정 (v0.35)
    "ultra":    {"mult": 2.0, "crf": 16, "preset": "fast", "sharpen": "cas"},
}
_SHARPEN = {"unsharp": "unsharp=5:5:0.8:5:5:0.0", "cas": "cas=0.55", True: "unsharp=5:5:0.8:5:5:0.0"}
_MAX_DIM = 3840  # 과도한 업스케일 방지 캡
# 잡음 제거(강도별): 저역 럼블 컷 + FFT 노이즈 리덕션 + 고역 히스 컷 (목소리 대역 보존)
DENOISE_LEVELS = {
    "low":  "highpass=f=70,afftdn=nr=10:nf=-25",
    "mid":  "highpass=f=85,afftdn=nr=18:nf=-28,lowpass=f=14500",
    "high": "highpass=f=100,afftdn=nr=30:nf=-32,lowpass=f=12000",
}


def _denoise_filter(denoise) -> str:
    """denoise 값(bool 또는 'low'|'mid'|'high') → 필터 문자열(끔이면 빈 문자열)."""
    if not denoise:
        return ""
    if denoise is True:
        return DENOISE_LEVELS["mid"]
    return DENOISE_LEVELS.get(str(denoise), "")


_FIXED_CANVAS = {"shorts": (1080, 1920), "wide": (1920, 1080)}  # 고정 캔버스 형태 (v0.77 가로 추가)


def _quality_canvas(layout: str, src_w: int, src_h: int, quality: str):
    """화질 등급 → (Canvas, crf, preset, sharpen). shorts/wide는 고정 캔버스, keep은 원본 기준 배수."""
    q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["standard"])
    base_w, base_h = _FIXED_CANVAS.get(layout, (src_w, src_h))
    mult = q["mult"]
    if layout not in _FIXED_CANVAS and max(base_w, base_h) > 0:  # keep: 최대 3840 캡
        mult = max(1.0, min(mult, _MAX_DIM / max(base_w, base_h)))
    w = int(round(base_w * mult)) & ~1
    h = int(round(base_h * mult)) & ~1
    return Canvas(w=w, h=h, fps=30), q["crf"], q["preset"], q["sharpen"]


def render_edited(
    cut_video: str,
    subtitles: List[Subtitle],
    out_path: str,
    style: Style,
    layout: str = "shorts",            # "shorts"(세로 1080x1920) | "wide"(가로 1920x1080, v0.77) | "keep"(원본 비율)
    hook: str = "",                    # 상단 제목(훅)
    fonts_dir: str = DEFAULT_FONTS_DIR,
    opts: Optional[RenderOptions] = None,
    speed: float = 1.0,                # 저장(렌더) 속도 배수 (1.25/1.5/2배 등)
    quality: str = "standard",         # 화질 등급: standard | high | ultra(4K)
    denoise=False,                     # 잡음 제거: False | True(중) | 'low'|'mid'|'high'
    narration_wav: Optional[str] = None,  # AI 내레이션 트랙(있으면 원본 소리는 덕킹)
    orig_audio: str = "keep",          # 원본 소리: keep(그대로) | low(작게) | mute(무음)
    bgm_path: Optional[str] = None,    # 배경음악 파일 (영상 길이만큼 루프 + 페이드)
    bgm_db: float = -16.0,             # BGM 볼륨(dB)
    bgm_duck: bool = False,            # 덕킹 — 목소리 나올 때 BGM 자동 감쇠 (v0.44)
    watermark: Optional[dict] = None,  # {path, pos(tr/tl/br/bl), scale, opacity} 로고 오버레이
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """컷 영상에 자동 자막을 번인. 영상 자체 오디오를 유지한다.

    speed>1이면 자막을 구운 뒤 영상·오디오를 통째로 배속 → 자막이 그대로 싱크 유지.
    quality가 high/ultra면 해상도·비트레이트↑ + 선명화(unsharp)로 화질을 올린다.
    denoise면 목소리 대역만 남기고 배경 잡음을 줄인다.
    """
    opts = opts or RenderOptions()
    speed = max(0.25, min(4.0, float(speed or 1.0)))
    src_w, src_h = ff.probe_video_size(cut_video)
    dur_us = ff.probe_duration_us(cut_video)
    has_src_audio = ff.has_audio_stream(cut_video)
    if narration_wav and orig_audio == "keep":
        orig_audio = "low"  # 하위호환: 내레이션이 있으면 원본은 배경으로 깔림

    canvas, crf, preset, sharpen = _quality_canvas(layout, src_w, src_h, quality)

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

    from .render_engine.ffmpeg_composer import TONE_PRESETS  # noqa: PLC0415

    tone_f = TONE_PRESETS.get(getattr(style, "tone", "기본") or "기본", "")
    subs_arg = (
        f"subtitles=filename={ff.escape_filter_value(str(ass_path))}"
        f":fontsdir={ff.escape_filter_value(str(fonts_dir))}"
    )
    # 워터마크(로고) — 자막보다 아래, 쇼츠 UI 안전영역을 피한 구석 배치
    wm = watermark if (watermark and watermark.get("path")
                       and Path(str(watermark["path"])).is_file()) else None
    wm_over = wm_pre = ""
    if wm:
        wm_w = max(2, int(canvas.w * float(wm.get("scale", 0.14)))) & ~1
        op = max(0.05, min(1.0, float(wm.get("opacity", 0.85))))
        mx = int(canvas.w * 0.03)
        top_y = int(canvas.h * (0.135 if layout == "shorts" else 0.03))
        bot_y = int(canvas.h * (0.235 if layout == "shorts" else 0.03))
        pos = str(wm.get("pos", "tr"))
        x = f"main_w-overlay_w-{mx}" if pos in ("tr", "br") else f"{mx}"
        y = f"{top_y}" if pos in ("tr", "tl") else f"main_h-overlay_h-{bot_y}"
        # 마지막 입력(영상[0], 내레이션?, BGM?, 워터마크) — 인덱스는 아래 _build_args와 동기
        wm_idx = 1 + (1 if narration_wav else 0) + (1 if bgm_path else 0)
        wm_pre = (f"[{wm_idx}:v]scale={wm_w}:-1,format=rgba,"
                  f"colorchannelmixer=aa={op:.2f}[wmimg];")
        wm_over = f"[wmimg]overlay={x}:{y}[wmk];[wmk]"
    if tone_f:  # 🎨 화면 톤 (v0.56) — 자막 굽기 직전 (글자는 원색 유지)
        subs_arg = f"{tone_f},{subs_arg}"
    sharp = f",{_SHARPEN[sharpen]}" if sharpen else ""  # 전경만 선명화(자막·블러배경은 제외)
    if layout in _FIXED_CANVAS:
        # 고정 캔버스(세로 쇼츠·가로 16:9): 블러 커버 배경 + 원본 비율 유지 전경 오버레이
        # (가로영상→세로, 세로영상→가로 모두 잘림 없이 자연스럽게)
        vf = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={canvas.w}:{canvas.h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={canvas.w}:{canvas.h},boxblur=24:2,eq=brightness=-0.1[bgb];"
            f"[fg]scale={canvas.w}:{canvas.h}:force_original_aspect_ratio=decrease:flags=lanczos{sharp}[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[comp];"
        )
        vf += (f"{wm_pre}[comp]{wm_over}{subs_arg}[vc]" if wm
               else f"[comp]{subs_arg}[vc]")
    else:
        vf = f"[0:v]scale={canvas.w}:{canvas.h}:flags=lanczos{sharp}[base];"
        vf += (f"{wm_pre}[base]{wm_over}{subs_arg}[vc]" if wm
               else f"[base]{subs_arg}[vc]")

    slow = abs(speed - 1.0) > 1e-3
    if slow:  # 자막 구운 뒤 영상 배속 (오디오는 아래 atempo)
        vf += f";[vc]setpts=PTS/{speed:.6f}[v]"
        vmap, out_us = "[v]", int(dur_us / speed)
    else:
        vmap, out_us = "[vc]", dur_us
    # 오디오 그래프: 원본(그대로/작게/무음, 잡음 제거) + 내레이션 + BGM(루프·페이드) → 배속
    dn = _denoise_filter(denoise)
    dur_s = dur_us / 1e6
    plain_passthrough = (
        not narration_wav and not bgm_path and orig_audio == "keep"
        and has_src_audio and not dn and not slow
    )
    if plain_passthrough:
        amap = "0:a"
    else:
        aparts, streams = [], []
        if orig_audio == "mute" or not has_src_audio:
            # 소리 제거(또는 오디오 트랙 없는 영상) → 같은 길이의 무음 트랙
            aparts.append(f"anullsrc=r=44100:cl=stereo:d={dur_s:.3f}[abase]")
        else:
            vol = 0.15 if orig_audio == "low" else 1.0
            dnf = f"{dn}," if dn else ""
            aparts.append(f"[0:a]{dnf}volume={vol}[abase]")
        streams.append("[abase]")
        nar_idx = 1
        if narration_wav:
            aparts.append(f"[{nar_idx}:a]apad[anar]")
            streams.append("[anar]")
        if bgm_path:
            bgm_idx = nar_idx + (1 if narration_wav else 0)
            gain = 10 ** (bgm_db / 20)
            fade_st = max(0.0, dur_s - 1.2)
            aparts.append(
                f"[{bgm_idx}:a]volume={gain:.4f},atrim=0:{dur_s:.3f},"
                f"afade=t=in:d=0.8,afade=t=out:st={fade_st:.3f}:d=1.2[abgm]")
            if bgm_duck:
                # 목소리(원본+내레이션)를 먼저 합치고 → BGM은 목소리가 나올 때
                # 자동으로 줄어들게(sidechaincompress) 한 뒤 합성 (v0.44 덕킹)
                if len(streams) > 1:
                    aparts.append(
                        "".join(streams)
                        + f"amix=inputs={len(streams)}:duration=first:normalize=0[avox]")
                else:
                    aparts.append(f"{streams[0]}anull[avox]")
                aparts.append("[avox]asplit[vmain][vside]")
                aparts.append("[abgm][vside]sidechaincompress="
                              "threshold=0.03:ratio=8:attack=20:release=300[abgmd]")
                streams = ["[vmain]", "[abgmd]"]
            else:
                streams.append("[abgm]")
        if len(streams) > 1:
            aparts.append(
                "".join(streams)
                + f"amix=inputs={len(streams)}:duration=first:normalize=0[apre]")
            last = "[apre]"
        else:
            last = "[abase]"
        if slow:
            aparts.append(f"{last}{_atempo_chain(speed)}[a]")
            last = "[a]"
        vf += ";" + ";".join(aparts)
        amap = last

    def _build_args(vcodec_args: list) -> list:
        a = ["-y", "-i", str(cut_video)]
        if narration_wav:
            a += ["-i", str(narration_wav)]
        if bgm_path:
            a += ["-stream_loop", "-1", "-i", str(bgm_path)]  # 영상 길이만큼 루프
        if wm:
            a += ["-i", str(wm["path"])]  # 워터마크 이미지 (wm_idx와 순서 동기)
        a += [
            "-filter_complex", vf,
            "-map", vmap, "-map", amap,
            *vcodec_args,
            "-pix_fmt", "yuv420p", "-r", str(canvas.fps),
            "-c:a", "aac", "-b:a", opts.audio_bitrate, "-movflags", "+faststart",
            str(out_path),
        ]
        return a

    cpu_args = ["-c:v", "libx264", "-crf", str(crf), "-preset", preset]
    if ff.nvenc_available():  # GPU 자동 사용 (몇 배 빠름) — 실패 시 CPU로 폴백
        gpu_args = ["-c:v", "h264_nvenc", "-preset", _NVENC_PRESETS.get(preset, "p5"),
                    "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
        try:
            ff.run_with_progress(_build_args(gpu_args), total_us=out_us, progress_cb=progress_cb)
            return str(out_path)
        except Exception:
            log.warning("GPU(nvenc) 렌더 실패 → CPU로 재시도")
    ff.run_with_progress(_build_args(cpu_args), total_us=out_us, progress_cb=progress_cb)
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
    out = []
    for s in subs:
        d = {"text": s.text, "start_us": s.start_us, "end_us": s.end_us,
             "highlight": s.highlight}
        if getattr(s, "words", None):   # 단어 시각·신뢰도 (v0.76) — 있을 때만 실어 가볍게
            d["words"] = [list(w) for w in s.words]
        if getattr(s, "conf", 1.0) < 0.999:
            d["conf"] = round(float(s.conf), 3)
        out.append(d)
    return out


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
        raw = (d.get("text") or "").strip()
        text, hl = split_highlight(raw)
        hl = (d.get("highlight") or hl or "").strip()
        if text:  # 빈 자막은 제외
            # 검토에서 글이 수정됐으면 단어 시각은 더 이상 안 맞음 → 버림 (카라오케는 폴백)
            words = d.get("words") or []
            joined = "".join(str(w[2]) for w in words if len(w) > 2)
            if words and _normalize_ko(joined) != _normalize_ko(text):
                words = []
            out.append(Subtitle(
                text=text, start_us=int(d["start_us"]), end_us=int(d["end_us"]),
                highlight=hl, words=[list(w) for w in words],
                conf=float(d.get("conf", 1.0)),
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


def analyze_narration_file(
    audio_path: str,
    workdir,
    stt: Optional[STTEngine] = None,
    script_lines: Optional[List[str]] = None,
    silence_opts: Optional[SilenceOptions] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> tuple:
    """녹음 내레이션 파일 → (자막 목록, 녹음 길이 μs) (v0.58).

    녹음은 최종 영상에서 0초부터 통째로 흐르므로 컷 없이 원본 타임라인 그대로
    자막 시각을 잡는다. 대본이 있으면 발화 구간에 그 글을 배치(비용 0·오인식 0),
    없으면 구간별 STT(문장 타임스탬프).
    """
    dur_us = ff.probe_duration_us(audio_path)
    try:
        segments, _ = video_editor.detect_speech_segments(audio_path, silence_opts)
    except Exception:  # noqa: BLE001 — 감지 실패면 전체를 한 구간으로
        segments = []
    if not segments:
        segments = [(0, dur_us)]
    clean = [ln.strip() for ln in (script_lines or []) if ln.strip()]
    if clean:
        return align_script_to_segments(clean, segments, total_us=dur_us), dur_us
    if stt is None:
        return [], dur_us
    pieces = transcribe_segments_timed(
        audio_path, segments, stt, Path(workdir),
        on_progress=(lambda i, n: progress_cb("stt", i / max(n, 1))) if progress_cb else None,
    )
    return build_subtitles_timed(segments, pieces), dur_us


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
        # v0.41: 문장 단위 타임스탬프 — 긴 발화 구간도 문장별로 자막이 바뀐다
        pieces = transcribe_segments_timed(
            video_path, segments, stt, work,
            on_progress=lambda i, n: report("stt", i / n),
        )
        subtitles = build_subtitles_timed(cut_segments, pieces)
        n_pieces = sum(len(p) for p in pieces)
        if n_pieces > len(segments):
            note(f"문장 단위 타임스탬프로 자막 {n_pieces}줄 (구간 {len(segments)}개)")
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
                    # 단어 시각은 자막 시작 기준 상대값 → 시프트에도 그대로 유효 (v0.76)
                    words=[list(w) for w in getattr(s, "words", [])],
                    conf=getattr(s, "conf", 1.0),
                ))
                break
    return out


# ── 🧹 말 다듬기 (v0.76) — 필러(추임새) 컷 + 반복(NG) 테이크 감지 ────────

# 한국어 추임새·군말 사전 — "독립적으로" 나온 것만 컷 (문장 속 조사·부사는 보호)
FILLER_WORDS = {
    "어", "어어", "음", "음음", "엄", "그", "저", "인제", "이제", "자",
    "그니까", "그러니까", "뭐지", "뭐랄까", "약간", "막",
}


def _normalize_ko(text: str) -> str:
    """비교용 정규화 — 공백·문장부호 제거."""
    import re as _re  # noqa: PLC0415

    return _re.sub(r"[\s.,!?~…·\-\"'()\[\]]+", "", str(text or ""))


def detect_filler_spans(subs: List[Subtitle], gap_us: int = 160_000,
                        min_dur_us: int = 120_000, pad_us: int = 40_000) -> List[tuple]:
    """단어 시각으로 '독립 추임새' 구간 찾기 → [(절대 시작μs, 끝μs, 단어), ...].

    안전 규칙: 사전에 있는 단어이면서 앞뒤로 gap_us 이상 떨어져 홀로 나온 것만.
    (문장 속에 붙어 나온 "그 사람"의 "그" 같은 건 건드리지 않는다 — 오버컷 방지)
    """
    spans: List[tuple] = []
    for s in subs:
        words = getattr(s, "words", None) or []
        for i, w in enumerate(words):
            wa, wb, wt = int(w[0]), int(w[1]), _normalize_ko(w[2])
            if wt not in FILLER_WORDS or (wb - wa) < min_dur_us:
                continue
            prev_end = int(words[i - 1][1]) if i > 0 else -10**12
            next_start = int(words[i + 1][0]) if i + 1 < len(words) else 10**12
            alone = (wa - prev_end >= gap_us or i == 0) and \
                    (next_start - wb >= gap_us or i + 1 == len(words))
            if alone:
                spans.append((s.start_us + max(0, wa - pad_us),
                              s.start_us + wb + pad_us, str(w[2])))
    spans.sort()
    merged: List[list] = []
    for a, b, t in spans:  # 겹침 병합
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b, t])
    return [tuple(m) for m in merged]


def apply_filler_cut(cut_video: str, subs: List[Subtitle], spans: List[tuple],
                     out_path: str) -> tuple:
    """필러 구간을 영상에서 잘라내고 자막(단어 시각 포함)을 새 타임라인으로 재매핑.

    반환: (새 영상 경로, 새 자막 목록). spans가 비면 원본 그대로.
    """
    if not spans:
        return cut_video, subs
    dur = ff.probe_duration_us(cut_video)
    cut = [(max(0, int(a)), min(dur, int(b))) for a, b, *_ in spans
           if int(b) > 0 and int(a) < dur]
    keep: List[tuple] = []
    cursor = 0
    for a, b in cut:
        if a > cursor:
            keep.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < dur:
        keep.append((cursor, dur))
    keep = [(a, b) for a, b in keep if b - a > 80_000]
    if not keep:
        return cut_video, subs
    video = video_editor.cut_and_concat(cut_video, keep, out_path)

    def removed_before(t: int) -> int:
        return sum(min(b, t) - a for a, b in cut if a < t)

    out_subs: List[Subtitle] = []
    for s in subs:
        words = []
        for w in (getattr(s, "words", None) or []):
            wa_abs, wb_abs = s.start_us + int(w[0]), s.start_us + int(w[1])
            mid = (wa_abs + wb_abs) // 2
            if any(a <= mid < b for a, b in cut):
                continue  # 잘려나간 단어(추임새)는 자막 텍스트에서도 제외
            words.append([wa_abs, wb_abs, str(w[2])])
        ns = s.start_us - removed_before(s.start_us)
        ne = s.end_us - removed_before(s.end_us)
        if ne - ns < 150_000:
            continue
        rel_words = [[max(0, wa - removed_before(wa) - ns),
                      max(0, wb - removed_before(wb) - ns), wt]
                     for wa, wb, wt in words]
        had_words = bool(getattr(s, "words", None))
        text = "".join(w[2] for w in rel_words).strip() if had_words else s.text
        # 공백 복원: whisper 단어는 보통 앞공백 포함이라 join으로 자연 복원되나,
        # 전부 사라졌으면 자막도 버린다
        if had_words and not text:
            continue
        out_subs.append(Subtitle(text=text or s.text, start_us=ns, end_us=ne,
                                 highlight=s.highlight if s.highlight in (text or s.text) else "",
                                 words=rel_words, conf=getattr(s, "conf", 1.0)))
    return video, out_subs


def detect_repeat_takes(texts: List[str], min_ratio: float = 0.8,
                        min_chars: int = 6) -> List[int]:
    """연속으로 거의 같은 말을 반복(NG 후 다시 말하기)한 앞 테이크들의 번호.

    인접(또는 한 칸 건너) 자막의 정규화 텍스트 유사도가 min_ratio 이상이면
    '같은 말 다시 하기'로 보고 앞쪽을 지우기 후보로 반환 (마지막 테이크 유지).
    """
    import difflib  # noqa: PLC0415

    norm = [_normalize_ko(t) for t in texts]
    drop: set = set()
    for i in range(len(norm) - 1):
        if len(norm[i]) < min_chars:
            continue
        for j in (i + 1, i + 2):
            if j >= len(norm) or len(norm[j]) < min_chars:
                continue
            ratio = difflib.SequenceMatcher(None, norm[i], norm[j]).ratio()
            if ratio >= min_ratio:
                drop.add(i)          # 뒤 테이크(다시 말한 쪽)를 남긴다
                break
    return sorted(drop)


def rebuild_from_keep(
    cut_video: str, subtitles: List[Subtitle], keep_idx: List[int], out_path: str,
    pad_us: int = 150_000, transition: str = "none",
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
    new_video = video_editor.cut_and_concat(cut_video, ranges, out_path,
                                            transition=transition)
    return new_video, _remap_subs_to_ranges(sorted(kept, key=lambda x: x.start_us), ranges)


def rebuild_cold_open(
    cut_video: str, subtitles: List[Subtitle], keep_idx: Optional[List[int]],
    out_path: str, climax_idx: int = -1, teaser_us: int = 2_800_000,
    pad_us: int = 150_000, transition: str = "none",
) -> tuple:
    """⚡ 콜드오픈 (v0.75) — 클라이맥스 2~3초를 맨 앞 티저로 놓고 본편(시간순)을 잇는다.

    알파컷식 'HOOK+CLIMAX': 가장 궁금한 순간을 먼저 슬쩍 보여주고 본편 시작.
    keep_idx=None이면 전체 자막이 본편. climax_idx가 무효면 후킹 점수로 자동 선택.
    티저를 만들 수 없으면(자막 1개·클라이맥스가 영상 첫머리 등) 일반 재컷과 동일.
    반환: (새 영상, 재매핑 자막, 티저 초 — 0.0이면 티저 없음)
    """
    idx = list(keep_idx) if keep_idx is not None else list(range(len(subtitles)))
    kept = [subtitles[i] for i in idx if 0 <= i < len(subtitles)]
    if not kept:
        raise ValueError("남길 자막을 하나 이상 선택하세요")
    kept_sorted = sorted(kept, key=lambda x: x.start_us)
    dur = ff.probe_duration_us(cut_video)
    ranges: List[tuple] = []
    for s in kept_sorted:
        a, b = max(0, s.start_us - pad_us), min(dur, s.end_us + pad_us)
        if ranges and a <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], b))
        else:
            ranges.append((a, b))
    # 클라이맥스 — 지정이 무효면 후킹 점수(숫자·질문·키워드)로 자동 선택
    if not (0 <= climax_idx < len(subtitles)) or climax_idx not in idx:
        from . import script_generator as sg  # noqa: PLC0415

        climax_idx = sg.pick_climax(subtitles_to_dicts(subtitles), sorted(set(idx)))
    climax = subtitles[climax_idx] if 0 <= climax_idx < len(subtitles) else None
    # 티저 불가 조건: 자막 1개뿐 / 클라이맥스가 사실상 영상 첫머리(티저 의미 없음)
    if (climax is None or len(kept_sorted) < 2
            or climax.start_us <= ranges[0][0] + 200_000):
        video, subs = rebuild_from_keep(cut_video, subtitles, idx, out_path,
                                        pad_us=pad_us, transition=transition)
        return video, subs, 0.0
    t_a = climax.start_us
    t_b = min(dur, min(climax.end_us + pad_us, t_a + teaser_us))
    if t_b - t_a < 700_000:  # 1초도 안 되는 티저는 오히려 어수선
        video, subs = rebuild_from_keep(cut_video, subtitles, idx, out_path,
                                        pad_us=pad_us, transition=transition)
        return video, subs, 0.0
    teaser_len = t_b - t_a
    # 티저 구간을 맨 앞에 — cut_and_concat은 주어진 순서 그대로 이어붙인다
    video = video_editor.cut_and_concat(cut_video, [(t_a, t_b)] + ranges, out_path,
                                        transition=transition)
    body = _remap_subs_to_ranges(kept_sorted, ranges)
    subs_out = [Subtitle(text=climax.text, highlight=climax.highlight,
                         start_us=0, end_us=teaser_len,
                         words=[list(w) for w in getattr(climax, "words", [])],
                         conf=getattr(climax, "conf", 1.0))]
    for s in body:
        subs_out.append(Subtitle(text=s.text, highlight=s.highlight,
                                 start_us=s.start_us + teaser_len,
                                 end_us=s.end_us + teaser_len,
                                 words=[list(w) for w in getattr(s, "words", [])],
                                 conf=getattr(s, "conf", 1.0)))
    return video, subs_out, teaser_len / 1e6


def split_long_subtitles(subs: List[Subtitle], wrap_chars: int = 16,
                         max_lines: int = 2) -> List[Subtitle]:
    """2줄(wrap_chars×max_lines자)을 넘는 자막을 여러 개의 짧은 자막으로 자동 분할.

    쇼츠 화면을 3~4줄 자막이 덮는 것 방지 — 단어 경계로 쪼개고 시간은 글자 수
    비례로 배분해 말 흐름과 싱크를 유지한다. 강조어는 그 단어가 든 조각에만 남긴다.
    """
    if wrap_chars <= 0 or max_lines <= 0:
        return list(subs)
    limit = wrap_chars * max_lines
    out: List[Subtitle] = []
    for s in subs:
        text = (s.text or "").strip()
        if len(text) <= limit:
            out.append(s)
            continue
        chunks: List[str] = []
        cur = ""
        for w in text.split():
            cand = f"{cur} {w}".strip()
            if len(cand) > limit and cur:
                chunks.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            chunks.append(cur)
        # 공백 없는 초장문(연속 문자열)은 단어 분할이 안 됨 → 글자 단위로 강제 분할
        fixed: List[str] = []
        for c in chunks:
            while len(c) > limit:
                fixed.append(c[:limit])
                c = c[limit:]
            fixed.append(c)
        chunks = [c for c in fixed if c]
        span = max(1, s.end_us - s.start_us)
        total_chars = sum(len(c) for c in chunks) or 1
        t = s.start_us
        for i, c in enumerate(chunks):
            if i == len(chunks) - 1:
                end = s.end_us
            else:
                end = min(t + max(span * len(c) // total_chars, 400_000), s.end_us)
            hl = s.highlight if s.highlight and s.highlight in c else ""
            out.append(Subtitle(text=c, start_us=t, end_us=max(end, t + 200_000), highlight=hl))
            t = out[-1].end_us
    return out


def extract_frames_b64(video: str, n: int = 4, width: int = 480) -> List[str]:
    """영상에서 고르게 n장 캡처 → base64 JPEG 목록 (AI 영상 분석 입력용)."""
    import base64
    import tempfile

    dur = ff.probe_duration_us(video) / 1e6
    out: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            at = dur * (i + 0.5) / n
            fp = Path(tmp) / f"f{i}.jpg"
            ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{at:.2f}",
                    "-i", str(video), "-frames:v", "1",
                    "-vf", f"scale={width}:-2", "-q:v", "5", str(fp)])
            if fp.is_file():
                out.append(base64.b64encode(fp.read_bytes()).decode("ascii"))
    return out


def spread_ranges(total_us: int, target_us: int, piece_us: int = 3_500_000) -> List[tuple]:
    """긴 영상 전체에서 고르게 조각을 뽑아 목표 길이를 채우는 구간 목록.

    자막(발화)이 없어 '핵심 선별'을 못 하는 영상(화면 녹화·b-roll)용 —
    앞부분만 자르는 대신 처음~끝을 고르게 보여주는 몽타주 컷.
    """
    total_us, target_us = int(total_us), int(target_us)
    if total_us <= target_us or target_us <= 0:
        return [(0, total_us)]
    n = max(1, round(target_us / piece_us))
    seg = target_us // n
    step = total_us / n
    ranges = []
    for i in range(n):
        start = int(i * step + (step - seg) / 2)
        start = max(0, min(start, total_us - seg))
        ranges.append((start, start + seg))
    return ranges


def retime_narration(clips: List, subtitles: List[Subtitle], total_us: int, tmp_dir,
                     lead_us: int = 200_000, max_tempo: float = 1.25,
                     fit: str = "drop") -> tuple:
    """자막 타이밍을 TTS 클립 '실제 길이'에 맞춰 순차 재배치 → 목소리·자막 싱크 보장.

    글자 수 비례로 추정한 창은 실제 발화 길이와 어긋나 자막이 밀리고 목소리가
    겹치거나 끝에서 잘린다. 실측 길이 기준으로:
      ① 남는 시간은 문장 사이 간격으로 고르게 배분 (0.12~0.9초)
      ② 영상보다 길면 말 속도를 최대 max_tempo배까지 올려 맞춤
      ③ 그래도 안 들어가는 뒷문장은 생략하고 사유를 알림
    fit이 "freeze"/"loop"면(v0.42) 영상을 뒤에서 늘릴 예정이므로 ②③을 하지 않고
    전 문장을 편한 간격으로 순차 배치한다 (넘침 허용 — 호출자가 영상을 연장).
    반환: (재배치된 자막들, 클립 경로들, 안내 문구 또는 "")
    """
    if not clips or not subtitles:
        return list(subtitles), [str(c) for c in clips], ""
    n = min(len(clips), len(subtitles))
    clips, subtitles = [str(c) for c in clips[:n]], list(subtitles[:n])
    durs = [ff.probe_duration_us(c) for c in clips]
    note = ""

    if fit in ("freeze", "loop"):
        # 영상 쪽을 늘려 다 담는다 → 속도 올림·생략 없이 순차 배치
        out_subs, out_clips, cursor = [], [], lead_us
        for clip, dur, sub in zip(clips, durs, subtitles):
            sub.start_us = cursor
            sub.end_us = cursor + dur
            out_subs.append(sub)
            out_clips.append(clip)
            cursor = sub.end_us + 350_000
        return out_subs, out_clips, ""

    min_gap = 120_000
    speech = sum(durs)
    if lead_us + speech + min_gap * (n - 1) > total_us:  # ② 넘치면 말 속도 up
        avail = max(1, total_us - lead_us - min_gap * (n - 1))
        tempo = min(max_tempo, speech / avail)
        if tempo > 1.01:
            tmp = Path(tmp_dir)
            tmp.mkdir(parents=True, exist_ok=True)
            sped = []
            for i, c in enumerate(clips):
                o = tmp / f"nar_tempo_{i:03d}.wav"
                ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", c,
                        "-af", _atempo_chain(tempo), "-c:a", "pcm_s16le", str(o)])
                sped.append(str(o))
            clips = sped
            durs = [ff.probe_duration_us(c) for c in clips]
            note = f"내레이션이 영상보다 길어 말 속도를 {tempo:.2f}배로 올렸어요"

    # ① 간격: 남는 시간을 문장 사이에 고르게 (너무 벌어지지 않게 상한)
    gap = 0
    if n > 1:
        gap = max(min_gap, min(900_000, (total_us - lead_us - sum(durs)) // (n - 1)))

    out_subs, out_clips, cursor, dropped = [], [], lead_us, 0
    for clip, dur, sub in zip(clips, durs, subtitles):
        if cursor + dur > total_us + 300_000 and out_subs:  # ③ 시작해도 못 끝내면 생략
            dropped += 1
            continue
        sub.start_us = cursor
        sub.end_us = min(cursor + dur, total_us)
        out_subs.append(sub)
        out_clips.append(clip)
        cursor = sub.start_us + dur + gap
    if dropped:
        extra = f"영상이 짧아 마지막 {dropped}문장은 생략했어요"
        note = f"{note} · {extra}" if note else extra
    return out_subs, out_clips, note


def build_narration_wav(clips: List, subtitles: List[Subtitle], total_us: int,
                        out_wav) -> str:
    """TTS 클립들을 각 자막 시작 시각에 배치해 하나의 내레이션 트랙으로 합침."""
    if not clips:
        raise ValueError("내레이션 클립이 없습니다")
    args = [ff.ffmpeg_bin(), "-y", "-v", "error"]
    parts, labels = [], []
    for i, (clip, sub) in enumerate(zip(clips, subtitles)):
        args += ["-i", str(clip)]
        ms = max(0, sub.start_us // 1000)
        parts.append(f"[{i}:a]adelay={ms}|{ms}[n{i}]")
        labels.append(f"[n{i}]")
    total_s = max(0.1, total_us / 1e6)
    fc = (
        ";".join(parts) + ";" + "".join(labels)
        + f"amix=inputs={len(labels)}:normalize=0,apad,atrim=0:{total_s:.3f}[a]"
    )
    args += ["-filter_complex", fc, "-map", "[a]", "-ar", "44100", str(out_wav)]
    ff.run(args)
    return str(out_wav)


def split_into_clips(subtitles: List[Subtitle], target_sec: float = 30.0,
                     min_last_sec: float = 6.0) -> List[List[int]]:
    """자막을 순서대로 목표 길이(초) 단위 그룹으로 나눔 → 쇼츠 여러 개 분할용.

    마지막 그룹이 너무 짧으면 앞 그룹에 합친다. 반환: 자막 번호 그룹 목록.
    """
    groups: List[List[int]] = []
    cur: List[int] = []
    cur_dur = 0.0
    for i, s in enumerate(subtitles):
        cur.append(i)
        cur_dur += max(0.0, (s.end_us - s.start_us) / 1e6)
        if cur_dur >= target_sec:
            groups.append(cur)
            cur, cur_dur = [], 0.0
    if cur:
        # 마지막 그룹 병합 기준은 목표 길이에 비례 (목표가 짧으면 기준도 낮춤)
        if groups and cur_dur < min(min_last_sec, target_sec * 0.5):
            groups[-1].extend(cur)
        else:
            groups.append(cur)
    return groups


def render_from_analysis(
    cut_video: str,
    subtitles: List[Subtitle],
    out_path: str,
    style: Optional[Style] = None,
    layout: str = "shorts",
    hook: str = "",
    opts: Optional[RenderOptions] = None,
    speed: float = 1.0,
    quality: str = "standard",
    denoise=False,
    narration_wav: Optional[str] = None,
    orig_audio: str = "keep",
    bgm_path: Optional[str] = None,
    bgm_db: float = -16.0,
    bgm_duck: bool = False,
    watermark: Optional[dict] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> EditResult:
    """2단계: (수정된) 자막으로 최종 렌더. speed 배속, quality 화질, denoise 잡음 제거."""
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
            speed=speed, quality=quality, denoise=denoise,
            narration_wav=narration_wav, orig_audio=orig_audio,
            bgm_path=bgm_path, bgm_db=bgm_db, bgm_duck=bgm_duck, watermark=watermark,
            progress_cb=progress_cb,
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
