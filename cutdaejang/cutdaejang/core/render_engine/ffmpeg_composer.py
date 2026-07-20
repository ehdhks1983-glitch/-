"""FFmpeg 필터그래프 조립·실행 (기획안 §5.5-3).

개념 구조:
    [배경]scale→setsar → [메인영상]scale → overlay → (그라데이션 overlay) → subtitles(ASS+fontsdir)
    비디오 libx264 crf19 / GPU 감지 시 h264_nvenc(cq 매핑), 오디오 AAC 192k, +faststart

- 메인 영상 없음(정보형 쇼츠): overlay 단계 생략, 배경+자막만
- 영상이 spec보다 김: trim / 짧음: short_policy에 따라 마지막 프레임 정지(tpad) 또는 루프
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ... import presets
from ...spec import TimelineSpec
from ...utils import ffmpeg as ff
from ...utils.timefmt import US_PER_SECOND, us_to_seconds_str


@dataclass
class RenderOptions:
    crf: int = 20               # 품질 (낮을수록 고품질·대용량)
    preset: str = "fast"        # 쇼츠 짧은 영상 — medium보다 빠르고 화질 차이 미미
    use_gpu: str = "auto"       # "auto" | "on" | "off"
    audio_bitrate: str = "192k"


# libx264 preset → nvenc preset 근사 매핑
_NVENC_PRESETS = {
    "ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "faster": "p4",
    "fast": "p4", "medium": "p5", "slow": "p6", "slower": "p7", "veryslow": "p7",
}


def build_command(
    spec: TimelineSpec,
    voice_path: str,
    ass_path: str,
    out_path: str,
    fonts_dir: str,
    gradient_path: Optional[str] = None,
    main_video_duration_us: Optional[int] = None,
    encoder: str = "libx264",
    opts: Optional[RenderOptions] = None,
) -> list:
    """ffmpeg 인자 목록(바이너리 제외) 생성 — 순수 함수 (실행은 compose가 담당).

    main_video_duration_us: 메인 영상의 ffprobe 실측 길이 (spec에 main_video가 있을 때 필수).
    """
    opts = opts or RenderOptions()
    c = spec.canvas
    dur_s = us_to_seconds_str(spec.duration_us)

    args: list = ["-y"]
    filters: list = []

    # ── 입력 0: 배경 (Ken Burns 모션 — 지시서 PATCH 4) ──
    motion = spec.background.motion if spec.background.type == "image" else "off"
    if spec.background.type == "image" and motion != "off":
        # 단일 프레임 입력 → zoompan이 프레임을 생성. 2배 사전 업스케일로 지터 방지.
        args += ["-i", spec.background.path]
        total_frames = math.ceil(spec.duration_us * c.fps / US_PER_SECOND)
        amt = spec.background.motion_amount
        if motion == "zoom_in":
            z_expr = f"min(1+{amt}*on/{total_frames},1+{amt})"
        else:  # zoom_out: 시작을 확대 상태에서 1.0으로
            z_expr = f"max(1+{amt}-{amt}*on/{total_frames},1)"
        # 지터 방지용 사전 업스케일. 2배는 저사양에서 과도하게 느려 1.5배로 낮춤
        # (60초 기준 38s→29s, 화질 차이 무시 가능). 짝수 보정.
        up_w = int(c.w * 1.5) & ~1
        up_h = int(c.h * 1.5) & ~1
        filters.append(
            f"[0:v]scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
            f"crop={up_w}:{up_h},"
            f"zoompan=z='{z_expr}'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={c.w}x{c.h}:fps={c.fps},setsar=1[bg]"
        )
    elif spec.background.type == "video":
        # v0.45 장면 슬라이드 배경 영상 — 캔버스 크기로 합성돼 오지만 안전하게 재정규화.
        # 몇 프레임 짧아도 마지막 프레임 복제(tpad)로 duration까지 채운다.
        args += ["-i", spec.background.path]
        filters.append(
            f"[0:v]scale={c.w}:{c.h}:force_original_aspect_ratio=increase,"
            f"crop={c.w}:{c.h},fps={c.fps},"
            f"tpad=stop_mode=clone:stop_duration=3,trim=duration={dur_s},"
            f"setpts=PTS-STARTPTS,setsar=1[bg]"
        )
    else:
        if spec.background.type == "image":
            args += ["-loop", "1", "-t", dur_s, "-i", spec.background.path]
        else:
            color = (spec.background.color or "#000000").replace("#", "0x")
            args += ["-f", "lavfi", "-i", f"color=c={color}:s={c.w}x{c.h}:r={c.fps}:d={dur_s}"]
        filters.append(
            f"[0:v]scale={c.w}:{c.h}:force_original_aspect_ratio=increase,"
            f"crop={c.w}:{c.h},setsar=1[bg]"
        )
    next_input = 1
    last_label = "bg"

    # ── 입력 1(선택): 메인 영상 ──
    if spec.main_video is not None:
        mv = spec.main_video
        if main_video_duration_us is None:
            raise ValueError("main_video가 있는 spec에는 main_video_duration_us가 필요합니다")
        loop_short = main_video_duration_us < spec.duration_us and mv.short_policy == "loop"
        if loop_short:
            args += ["-stream_loop", "-1", "-i", mv.path]
        else:
            args += ["-i", mv.path]
        mv_idx = next_input
        next_input += 1

        chain = []
        if main_video_duration_us > spec.duration_us or loop_short:
            chain.append(f"trim=duration={dur_s},setpts=PTS-STARTPTS")
        elif main_video_duration_us < spec.duration_us:  # freeze_last
            delta = spec.duration_us - main_video_duration_us
            chain.append(
                f"tpad=stop_mode=clone:stop_duration={us_to_seconds_str(delta)}"
            )
        if mv.layout == "full":
            chain.append(
                f"scale={c.w}:{c.h}:force_original_aspect_ratio=increase,crop={c.w}:{c.h}"
            )
        else:
            chain.append(f"scale={presets.main_video_target_width(c.w, mv.layout, mv.scale)}:-2")
        filters.append(f"[{mv_idx}:v]" + ",".join(chain) + "[mv]")

        y = "0" if mv.layout == "full" else presets.main_video_y_expr(mv.layout, c.h)
        filters.append(f"[{last_label}][mv]overlay=x=(W-w)/2:y={y}[comp]")
        last_label = "comp"

    # ── 입력: 병합 보이스 ──
    args += ["-i", str(voice_path)]
    voice_idx = next_input
    next_input += 1

    # ── 입력(선택): BGM (지시서 PATCH 3) — 루프·감쇠·페이드·무손실 믹스 ──
    audio_map = f"{voice_idx}:a"
    if spec.bgm is not None:
        args += ["-stream_loop", "-1", "-i", spec.bgm.path]
        bgm_idx = next_input
        next_input += 1
        fade_out_st = max(0.0, spec.duration_us / US_PER_SECOND - 1.5)
        bgm_chain = (
            f"[{bgm_idx}:a]volume={spec.bgm.volume_db}dB,atrim=0:{dur_s},"
            f"afade=t=in:d=0.5,afade=t=out:st={fade_out_st:.3f}:d=1.5"
        )
        if spec.bgm.duck:
            filters.append(f"[{voice_idx}:a]asplit[vmain][vside]")
            filters.append(bgm_chain + "[bgm0]")
            filters.append(
                "[bgm0][vside]sidechaincompress="
                "threshold=0.03:ratio=8:attack=20:release=300[bgduck]"
            )
            # normalize=0 필수 — amix 기본 동작이 음성 볼륨을 깎는다
            filters.append("[vmain][bgduck]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            filters.append(bgm_chain + "[bgma]")
            filters.append(
                f"[{voice_idx}:a][bgma]amix=inputs=2:duration=first:normalize=0[aout]"
            )
        audio_map = "[aout]"

    # ── 입력(선택): 하단 그라데이션 오버레이 ──
    if gradient_path:
        args += ["-loop", "1", "-t", dur_s, "-i", str(gradient_path)]
        filters.append(f"[{last_label}][{next_input}:v]overlay=x=0:y=0[grad]")
        last_label = "grad"
        next_input += 1

    # ── 👊 펀치인 줌 (v0.55) — 강조 문장 구간에서 화면이 살짝 확대됐다 복귀.
    # 자막 굽기 전에 적용해 자막·제목은 고정(가독성). on(출력 프레임 번호) 기반이라
    # ffmpeg 버전 무관, zoom 변수로 램프 인(빠르게)/아웃(부드럽게).
    if getattr(spec, "punchins", None):
        filters.append(
            f"[{last_label}]zoompan=z={punch_zoom_expr(spec.punchins, c.fps)}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={c.w}x{c.h}:fps={c.fps}[punch]"
        )
        last_label = "punch"

    # ── 자막 번인 (libass) ──
    filters.append(
        f"[{last_label}]subtitles=filename={ff.escape_filter_value(str(ass_path))}"
        f":fontsdir={ff.escape_filter_value(str(fonts_dir))}[v]"
    )

    # ── 인코딩 ──
    if encoder == "h264_nvenc":
        video_args = [
            "-c:v", "h264_nvenc",
            "-preset", _NVENC_PRESETS.get(opts.preset, "p5"),
            "-rc", "vbr", "-cq", str(opts.crf), "-b:v", "0",
        ]
    else:
        video_args = ["-c:v", "libx264", "-crf", str(opts.crf), "-preset", opts.preset]

    args += [
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", audio_map,
        *video_args,
        "-pix_fmt", "yuv420p", "-r", str(c.fps),
        "-c:a", "aac", "-b:a", opts.audio_bitrate,
        "-movflags", "+faststart",
        "-t", dur_s,
        str(out_path),
    ]
    return args


PUNCH_SCALE = 1.10   # 펀치인 최대 배율 (v0.55)


def punch_zoom_expr(punchins, fps: int) -> str:
    """펀치 구간 → zoompan z 식. on(출력 프레임 번호)/fps 기반이라 버전 무관.

    구간 안: 프레임당 +0.012씩 1.10까지 (약 0.28초 램프 인)
    구간 밖: 프레임당 -0.008씩 1.0으로 (약 0.42초 램프 아웃 — 부드럽게)
    """
    wins = "+".join(
        f"between(on,{int(p.start_us * fps / 1_000_000)},{int(p.end_us * fps / 1_000_000)})"
        for p in punchins)
    return (f"'if({wins},min(zoom+0.012,{PUNCH_SCALE}),max(zoom-0.008,1.0))'")


def pick_encoder(opts: RenderOptions) -> str:
    """GPU 자동 감지 — h264_nvenc 사용 가능 시 전환, 아니면 libx264 (기획안 §5.5-3)."""
    if opts.use_gpu == "off":
        return "libx264"
    if opts.use_gpu == "on":
        return "h264_nvenc"
    return "h264_nvenc" if ff.nvenc_available() else "libx264"


def compose(
    spec: TimelineSpec,
    voice_path: str,
    ass_path: str,
    out_path: str,
    fonts_dir: str,
    gradient_path: Optional[str] = None,
    opts: Optional[RenderOptions] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """합성 실행. nvenc 경로 실패 시 libx264로 1회 폴백. 사용한 인코더를 반환."""
    opts = opts or RenderOptions()
    mv_dur = (
        ff.probe_duration_us(spec.main_video.path) if spec.main_video is not None else None
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    encoder = pick_encoder(opts)
    try:
        ff.run_with_progress(
            build_command(
                spec, voice_path, ass_path, out_path, fonts_dir,
                gradient_path=gradient_path, main_video_duration_us=mv_dur,
                encoder=encoder, opts=opts,
            ),
            total_us=spec.duration_us,
            progress_cb=progress_cb,
        )
    except ff.FFmpegError:
        if encoder != "h264_nvenc":
            raise
        encoder = "libx264"  # GPU 경로 실패 → CPU 폴백
        ff.run_with_progress(
            build_command(
                spec, voice_path, ass_path, out_path, fonts_dir,
                gradient_path=gradient_path, main_video_duration_us=mv_dur,
                encoder=encoder, opts=opts,
            ),
            total_us=spec.duration_us,
            progress_cb=progress_cb,
        )
    return encoder
