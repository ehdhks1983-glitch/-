"""문장별 TTS 클립 + 갭 무음 → 단일 오디오 트랙 병합 (기획안 §5.5-1).

각 클립을 샘플 단위(adelay=...S)로 스펙의 start_us 위치에 배치하고 무손실 합산(amix
normalize=0) 후 스펙 길이에 맞춰 패딩/트림한다. 1회 재인코딩으로 ``voice_full.m4a``
(AAC 192k, 48kHz 스테레오)를 만들고, ffprobe 실측 길이를 스펙 길이와 대조한다.
"""

from __future__ import annotations

from pathlib import Path

from ...spec import TimelineSpec
from ...utils import ffmpeg as ff
from ...utils.timefmt import us_to_samples, us_to_seconds_str


class AssembleError(RuntimeError):
    pass


def build_command(spec: TimelineSpec, out_path: str) -> list:
    """ffmpeg 인자 목록(바이너리 제외) 생성 — 테스트 가능하도록 순수 함수로 분리."""
    dur_s = us_to_seconds_str(spec.duration_us)
    args: list = ["-y"]
    filters = []

    if not spec.audio:
        args += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={dur_s}"]
        filters.append("[0:a]atrim=end=" + dur_s + "[aout]")
    else:
        for clip in spec.audio:
            args += ["-i", clip.path]
        labels = []
        for i, clip in enumerate(spec.audio):
            delay = us_to_samples(clip.start_us)
            filters.append(
                f"[{i}:a]aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"adelay=delays={delay}S:all=1[a{i}]"
            )
            labels.append(f"[a{i}]")
        filters.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:normalize=0:duration=longest[mix]"
        )
        filters.append(f"[mix]apad,atrim=end={dur_s}[aout]")

    args += [
        "-filter_complex", ";".join(filters),
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return args


def assemble(spec: TimelineSpec, out_path, tolerance_us: int = 50_000) -> int:
    """병합 실행 후 실측 길이(μs) 반환. 스펙 길이와 tolerance 초과 차이면 AssembleError."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.run([ff.ffmpeg_bin(), *build_command(spec, str(out))])

    measured = ff.probe_duration_us(str(out))
    diff = abs(measured - spec.duration_us)
    if diff > tolerance_us:
        raise AssembleError(
            f"병합 오디오 길이 불일치: 실측 {measured}μs vs 스펙 {spec.duration_us}μs "
            f"(오차 {diff}μs > 허용 {tolerance_us}μs)"
        )
    return measured
