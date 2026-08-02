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
from ..utils.ffmpeg import edge_silence_us, probe_duration_us

# 아무리 줄여도 문장 사이에 이만큼은 남긴다 (edit_mode와 같은 값)
MIN_HEARD_GAP_US = 90_000


@dataclass
class TimelineOptions:
    lead_in_us: int = 300_000   # 첫 문장 전 여백
    gap_us: int = 250_000       # 문장 간격 (설정 탭에서 조정 가능, §6 탭④)
    pace_to_us: int = 0         # 0이 아니면 문장 간격을 늘려 이 길이에 맞춤 (v0.63, 늘리기만)
    tail_us: int = 600_000      # 마지막 문장 뒤 패딩
    # 🔗 v1.27: joins[i]가 True면 i번과 i+1번 줄 사이는 간격 0 — 같은 문장을
    # 자막 두 줄로 쪼갠 자리다. 여기에 침묵이 들어가면 문장 한가운데가 끊겨 들린다.
    joins: Optional[List[bool]] = None


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
    joins = list(opts.joins or [])          # 🔗 v1.27 — 붙일 자리
    gap_us = opts.gap_us

    def joined(i: int) -> bool:
        """i번 줄과 다음 줄이 같은 문장이라 붙여야 하나 (v1.27)."""
        return i < len(joins) and bool(joins[i])

    # 실제로 간격이 들어가는 경계 수 — 붙이는 자리는 빼고 센다
    gaps_n = sum(1 for i in range(max(0, len(sentences) - 1)) if not joined(i))
    if opts.pace_to_us and gaps_n > 0:
        # ⏱ 목표 길이 맞추기 (v0.63) — 말 자체는 못 줄이니 간격을 늘려서만 맞춘다.
        # 경계당 최대 2.5초까지(어색한 침묵 방지), 남는 초과분은 tail에서 흡수.
        speech = sum(probe_duration_us(str(Path(pp))) for pp in audio_paths)
        raw = opts.lead_in_us + speech + opts.gap_us * gaps_n + opts.tail_us
        extra = opts.pace_to_us - raw
        if extra > 0:
            gap_us = opts.gap_us + min(2_500_000, extra // gaps_n)
    # 🔇 v1.31 (목록 61): 클립 앞뒤에 이미 붙어 있는 무음을 빼야 «들리는» 간격이
    #   우리가 정한 값이 된다. 안 빼면 250ms로 적어 놓고 350ms가 들린다.
    edges = [edge_silence_us(str(Path(pp))) for pp in audio_paths]

    def pad(i: int) -> int:
        return edges[i][1] + (edges[i + 1][0] if i + 1 < len(edges) else 0)

    t = opts.lead_in_us
    last_gap = 0
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
        # ⚠ 목표 길이 맞추기(pace_to_us)로 간격을 일부러 늘린 경우엔 빼지 않는다 —
        #    그 간격은 «들리는 쉼»이 아니라 «영상 길이를 채우는 수단»이다.
        last_gap = 0 if joined(i) else (
            gap_us if opts.pace_to_us else max(MIN_HEARD_GAP_US, gap_us - pad(i)))
        t += dur + last_gap

    duration_us = (t - last_gap) + opts.tail_us if audio else opts.lead_in_us + opts.tail_us

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
