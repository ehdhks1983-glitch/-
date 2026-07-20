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
    pace_to_us: int = 0         # 0이 아니면 문장 간격을 늘려 이 길이에 맞춤 (v0.63, 늘리기만)
    tail_us: int = 600_000      # 마지막 문장 뒤 패딩


def build_spec(
    sentences: List[str],
    audio_paths: List[str],
    background: Background,
    style: Style,
    canvas: Optional[Canvas] = None,
    main_video: Optional[MainVideo] = None,
    bgm=None,
    highlights: Optional[List[str]] = None,
    hook: str = "",
    mode: str = "shorts",
    opts: Optional[TimelineOptions] = None,
) -> TimelineSpec:
    if len(sentences) != len(audio_paths):
        raise ValueError(f"문장 수({len(sentences)})와 오디오 수({len(audio_paths)}) 불일치")
    canvas = canvas or Canvas()
    opts = opts or TimelineOptions()
    highlights = highlights or []

    audio: List[AudioClip] = []
    subtitles: List[Subtitle] = []
    gap_us = opts.gap_us
    if opts.pace_to_us and len(sentences) > 1:
        # ⏱ 목표 길이 맞추기 (v0.63) — 말 자체는 못 줄이니 간격을 늘려서만 맞춘다.
        # 경계당 최대 2.5초까지(어색한 침묵 방지), 남는 초과분은 tail에서 흡수.
        speech = sum(probe_duration_us(str(Path(pp))) for pp in audio_paths)
        raw = opts.lead_in_us + speech + opts.gap_us * (len(sentences) - 1) + opts.tail_us
        extra = opts.pace_to_us - raw
        if extra > 0:
            gap_us = opts.gap_us + min(2_500_000, extra // (len(sentences) - 1))
    t = opts.lead_in_us
    for i, (text, path) in enumerate(zip(sentences, audio_paths)):
        dur = probe_duration_us(str(Path(path)))
        audio.append(AudioClip(path=str(path), start_us=t, end_us=t + dur))
        subtitles.append(
            Subtitle(
                text=text,
                start_us=t,
                end_us=t + dur,
                highlight=highlights[i] if i < len(highlights) else "",
            )
        )
        t += dur + gap_us

    duration_us = (t - gap_us) + opts.tail_us if audio else opts.lead_in_us + opts.tail_us

    return TimelineSpec(
        mode=mode,
        canvas=canvas,
        duration_us=duration_us,
        hook=hook,
        background=background,
        main_video=main_video,
        bgm=bgm,
        audio=audio,
        subtitles=subtitles,
        style=style,
    ).validate()
