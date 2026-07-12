"""문장별 TTS 실측(ffprobe) → Timeline Spec 확정 (기획안 §3.3, §5 ④).

start/end는 실측 길이의 누적으로만 계산하고, 자막은 오디오와 동일 timerange를 갖는다
→ 동기화 오차 0. 모든 값은 μs 정수.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..spec import (
    AudioClip,
    Background,
    Canvas,
    MainVideo,
    Style,
    Subtitle,
    TimelineSpec,
)
from ..utils.ffmpeg import probe_duration_us


@dataclass
class TimelineOptions:
    lead_in_us: int = 300_000   # 첫 문장 전 여백
    gap_us: int = 250_000       # 문장 간격 (설정 탭에서 조정 가능, §6 탭④)
    tail_us: int = 600_000      # 마지막 문장 뒤 패딩


def build_spec(
    sentences: List[str],
    audio_paths: List[str],
    background: Background,
    style: Style,
    canvas: Optional[Canvas] = None,
    main_video: Optional[MainVideo] = None,
    mode: str = "shorts",
    opts: Optional[TimelineOptions] = None,
) -> TimelineSpec:
    if len(sentences) != len(audio_paths):
        raise ValueError(f"문장 수({len(sentences)})와 오디오 수({len(audio_paths)}) 불일치")
    canvas = canvas or Canvas()
    opts = opts or TimelineOptions()

    audio: List[AudioClip] = []
    subtitles: List[Subtitle] = []
    t = opts.lead_in_us
    for text, path in zip(sentences, audio_paths):
        dur = probe_duration_us(str(Path(path)))
        audio.append(AudioClip(path=str(path), start_us=t, end_us=t + dur))
        subtitles.append(Subtitle(text=text, start_us=t, end_us=t + dur))
        t += dur + opts.gap_us

    duration_us = (t - opts.gap_us) + opts.tail_us if audio else opts.lead_in_us + opts.tail_us

    return TimelineSpec(
        mode=mode,
        canvas=canvas,
        duration_us=duration_us,
        background=background,
        main_video=main_video,
        audio=audio,
        subtitles=subtitles,
        style=style,
    ).validate()
