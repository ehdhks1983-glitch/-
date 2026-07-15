"""내 영상 편집 — 무음 구간 감지·컷 + 발화 구간 추출 (기획안 v1.5 육성 촬영 모드).

핵심 아이디어: **타이밍은 무음 감지(FFmpeg silencedetect, 매우 정확)에서, 자막 글자는
음성인식(STT)에서** 가져온다. 이러면 STT 제공자의 타임스탬프 정확도에 의존하지 않고도
자막 싱크가 정확하다.

파이프라인:
  ① detect_speech_segments: 원본 영상 → 발화 구간 [(start_us, end_us), ...]
  ② cut_and_concat: 발화 구간만 이어붙인 컷 영상(오디오 포함) 생성
  ③ (호출측) 각 발화 구간 오디오를 STT → 자막 텍스트, 컷 후 새 타임라인에 배치
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from ..utils import ffmpeg as ff
from ..utils.timefmt import US_PER_SECOND, seconds_to_us, us_to_seconds_str


VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv",
              ".mpg", ".mpeg", ".ts", ".m2ts"}


def resolve_input_video(path: str) -> str:
    """입력 경로를 실제 영상 파일로 해석.

    - 파일이면 그대로.
    - 폴더면 안의 영상 파일을 찾아: 1개면 사용, 여러 개면 최신 파일 사용(안내는 호출측).
    - 없으면 친절한 오류(ValueError).
    """
    p = Path((path or "").strip().strip('"'))
    if p.is_file():
        return str(p)
    if p.is_dir():
        vids = sorted(
            (f for f in p.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTS),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not vids:
            raise ValueError(
                f"'{p}'는 폴더인데 안에 영상 파일이 없습니다. 영상 파일(.mp4 등)을 직접 지정하세요."
            )
        return str(vids[0])  # 가장 최근 영상 (Bandicam 등 녹화 폴더 대응)
    raise ValueError(
        f"영상을 찾을 수 없습니다: {path}\n"
        "파일 탐색기에서 영상 파일 우클릭 → '경로로 복사' 후 붙여넣으세요 (…\\영상이름.mp4)."
    )


@dataclass
class SilenceOptions:
    noise_db: int = -30          # 이보다 조용하면 무음으로 간주
    min_silence_s: float = 0.5   # 이 길이 이상 지속돼야 컷 대상 무음
    pad_s: float = 0.10          # 발화 구간 앞뒤 여유 (말 잘림 방지)
    min_segment_s: float = 0.30  # 이보다 짧은 발화 조각은 버림(노이즈)
    max_segment_s: float = 6.0   # 이보다 길면 자막 가독성 위해 분할


_SIL_START = re.compile(r"silence_start:\s*([-\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([-\d.]+)")


def _parse_silences(stderr_text: str) -> List[Tuple[float, float]]:
    """silencedetect stderr → [(start_s, end_s), ...] (초 단위)."""
    starts = [float(m) for m in _SIL_START.findall(stderr_text)]
    ends = [float(m) for m in _SIL_END.findall(stderr_text)]
    # start가 end보다 하나 많을 수 있음(영상 끝까지 무음) → 그 경우는 무시(끝 패딩)
    return list(zip(starts, ends))


def detect_silences(video_path: str, opts: SilenceOptions) -> List[Tuple[float, float]]:
    """silencedetect 실행 → 무음 구간(초) 목록. run()이 stderr를 안전하게 수집한다."""
    proc = ff.run(
        [
            ff.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(video_path),
            "-af", f"silencedetect=noise={opts.noise_db}dB:d={opts.min_silence_s}",
            "-f", "null", "-",
        ]
    )
    return _parse_silences(proc.stderr.decode("utf-8", "replace"))


def speech_from_silences(
    duration_us: int, silences: List[Tuple[float, float]], opts: SilenceOptions
) -> List[Tuple[int, int]]:
    """무음 구간의 여집합 = 발화 구간. 패딩·최소길이·최대길이 정책 적용 (μs)."""
    pad = opts.pad_s
    # 무음 구간을 μs로, 정렬
    sil_us = sorted(
        (max(0, seconds_to_us(s)), min(duration_us, seconds_to_us(e)))
        for s, e in silences
        if e > s
    )
    # 여집합 구하기
    speech: List[Tuple[int, int]] = []
    cursor = 0
    for s, e in sil_us:
        if s > cursor:
            speech.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration_us:
        speech.append((cursor, duration_us))

    # 패딩(무음 쪽으로 살짝 확장) + 최소길이 필터 + 인접 병합
    pad_us = seconds_to_us(pad)
    padded: List[Tuple[int, int]] = []
    for s, e in speech:
        s2 = max(0, s - pad_us)
        e2 = min(duration_us, e + pad_us)
        if padded and s2 <= padded[-1][1]:  # 패딩으로 겹치면 병합
            padded[-1] = (padded[-1][0], max(padded[-1][1], e2))
        else:
            padded.append((s2, e2))

    min_us = seconds_to_us(opts.min_segment_s)
    kept = [(s, e) for s, e in padded if e - s >= min_us]

    # 너무 긴 구간은 자막 가독성 위해 분할
    max_us = seconds_to_us(opts.max_segment_s)
    result: List[Tuple[int, int]] = []
    for s, e in kept:
        if e - s <= max_us:
            result.append((s, e))
            continue
        n = -(-(e - s) // max_us)  # ceil
        step = (e - s) // n
        for i in range(n):
            seg_s = s + i * step
            seg_e = e if i == n - 1 else s + (i + 1) * step
            result.append((seg_s, seg_e))
    return result


def detect_speech_segments(
    video_path: str, opts: Optional[SilenceOptions] = None
) -> Tuple[List[Tuple[int, int]], int]:
    """영상 → (발화 구간 목록 μs, 원본 길이 μs)."""
    opts = opts or SilenceOptions()
    duration_us = ff.probe_duration_us(str(video_path))
    silences = detect_silences(str(video_path), opts)
    segments = speech_from_silences(duration_us, silences, opts)
    if not segments:  # 전부 무음/조용 → 통째로 한 구간 (컷 없음)
        segments = [(0, duration_us)]
    return segments, duration_us


def remap_to_cut_timeline(segments: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """컷 후 새 타임라인에서 각 구간의 (start_us, end_us). 무음 제거 누적."""
    out: List[Tuple[int, int]] = []
    cursor = 0
    for s, e in segments:
        dur = e - s
        out.append((cursor, cursor + dur))
        cursor += dur
    return out


def cut_and_concat(
    video_path: str, segments: List[Tuple[int, int]], out_path: str, fps: int = 30
) -> str:
    """발화 구간만 잘라 이어붙인 영상(오디오 포함) 생성. trim+concat 재인코딩."""
    if not segments:
        raise ValueError("자를 발화 구간이 없습니다")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    parts = []
    labels = []
    for i, (s, e) in enumerate(segments):
        ss, se = us_to_seconds_str(s), us_to_seconds_str(e)
        parts.append(
            f"[0:v]trim=start={ss}:end={se},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={ss}:end={se},asetpts=PTS-STARTPTS[a{i}]"
        )
        labels.append(f"[v{i}][a{i}]")
    concat = "".join(labels) + f"concat=n={len(segments)}:v=1:a=1[v][a]"
    filtergraph = ";".join(parts) + ";" + concat

    # 중간 산출물(최종 렌더에서 다시 인코딩됨) → ultrafast + 저손실 crf18로 속도 우선
    ff.run(
        [
            ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(video_path),
            "-filter_complex", filtergraph,
            "-map", "[v]", "-map", "[a]",
            "-r", str(fps),
            "-c:v", "libx264", "-crf", "18", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(out_path),
        ]
    )
    return str(out_path)


def extract_segment_audio(video_path: str, start_us: int, end_us: int, out_wav: str) -> str:
    """원본 영상에서 한 발화 구간의 오디오만 wav로 추출 (구간별 STT 입력용, 16kHz mono)."""
    ff.run(
        [
            ff.ffmpeg_bin(), "-y", "-v", "error",
            "-ss", us_to_seconds_str(start_us), "-to", us_to_seconds_str(end_us),
            "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(out_wav),
        ]
    )
    return str(out_wav)


def silence_ratio(segments: List[Tuple[int, int]], duration_us: int) -> float:
    """제거될 무음 비율 (0~1) — 리포트용."""
    kept = sum(e - s for s, e in segments)
    return max(0.0, 1.0 - kept / duration_us) if duration_us else 0.0
