"""
video_converter.py - 영상 → GIF/WebP/APNG 변환 코어
FFmpeg subprocess 기반, 프레임 단위 진행률 콜백
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from utils import find_ffmpeg, find_ffprobe, run_ffmpeg, format_filesize


class VideoInfo:
    """영상 메타데이터"""

    def __init__(self):
        self.width: int = 0
        self.height: int = 0
        self.duration: float = 0.0       # 초
        self.fps: float = 0.0
        self.codec: str = ""
        self.file_size: int = 0
        self.format_name: str = ""
        self.has_audio: bool = False

    @property
    def duration_str(self) -> str:
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def resolution_str(self) -> str:
        return f"{self.width}x{self.height}"

    def summary(self) -> str:
        return (
            f"{self.resolution_str} | {self.fps:.1f}fps | "
            f"{self.duration_str} | {format_filesize(self.file_size)}"
        )


class Subtitle:
    """자막 한 줄"""
    def __init__(self, text: str = "", start: float = 0.0, end: float = 0.0,
                 position: str = "bottom", size: int = 32, color: str = "#FFFFFF",
                 bold: bool = True):
        self.text = text
        self.start = start
        self.end = end
        self.position = position  # top / middle / bottom
        self.size = size
        self.color = color
        self.bold = bold


class ConvertJob:
    """영상 변환 작업 설정"""

    def __init__(self):
        self.input_path: str = ""
        self.output_path: str = ""
        self.output_format: str = "gif"    # gif / webp / apng / mp4
        self.start_time: float = 0.0       # 초
        self.end_time: float = 0.0         # 초 (0 = 끝까지)
        self.fps: int = 15                 # 출력 FPS
        self.width: int = 0                # 0 = 원본
        self.height: int = -1              # -1 = 비율 유지
        self.quality: int = 80
        self.speed: float = 1.0            # 0.5x ~ 2.0x
        self.loop: int = 0                 # 0 = 무한
        self.cancelled: bool = False
        self.subtitles: list = []          # List[Subtitle]
        self.output_height: int = 480      # 출력 높이 (자막 크기 정규화용)
        self.shorts_vertical: bool = False  # MP4 쇼츠(세로 9:16) 모드


def probe_video(path: str) -> Optional[VideoInfo]:
    """ffprobe로 영상 정보 추출"""
    ffprobe = find_ffprobe()
    if not ffprobe:
        # ffprobe 없으면 ffmpeg -i 로 폴백
        return _probe_fallback(path)

    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        path,
    ]

    try:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": 30}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        r = subprocess.run(cmd, **kwargs)
        data = json.loads(r.stdout.decode('utf-8', errors='replace'))

        info = VideoInfo()
        info.file_size = Path(path).stat().st_size

        # format
        fmt = data.get("format", {})
        info.duration = float(fmt.get("duration", 0))
        info.format_name = fmt.get("format_name", "")

        # streams
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and info.width == 0:
                info.width = int(stream.get("width", 0))
                info.height = int(stream.get("height", 0))
                info.codec = stream.get("codec_name", "")
                # FPS 파싱
                fps_str = stream.get("r_frame_rate", "0/1")
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    info.fps = float(num) / max(1, float(den))
                else:
                    info.fps = float(fps_str)
            elif stream.get("codec_type") == "audio":
                info.has_audio = True

        return info if info.width > 0 else None

    except Exception:
        return _probe_fallback(path)


def _probe_fallback(path: str) -> Optional[VideoInfo]:
    """ffmpeg -i 로 영상 정보 추출 (ffprobe 없을 때)"""
    ff = find_ffmpeg()
    if not ff:
        return None

    cmd = [ff, "-i", path]
    try:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": 15, "check": False}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        r = subprocess.run(cmd, **kwargs)
        stderr = r.stderr.decode('utf-8', errors='replace')

        info = VideoInfo()
        info.file_size = Path(path).stat().st_size

        # Duration: 00:01:23.45
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', stderr)
        if m:
            h, mn, s, cs = int(m[1]), int(m[2]), int(m[3]), int(m[4])
            info.duration = h * 3600 + mn * 60 + s + cs / 100

        # Video: h264 ... 1920x1080 ... 30 fps
        m2 = re.search(r'Video:.*?(\w+).*?(\d{2,5})x(\d{2,5})', stderr)
        if m2:
            info.codec = m2[1]
            info.width = int(m2[2])
            info.height = int(m2[3])

        m3 = re.search(r'(\d+(?:\.\d+)?)\s*fps', stderr)
        if m3:
            info.fps = float(m3[1])

        if "Audio:" in stderr:
            info.has_audio = True

        return info if info.width > 0 else None

    except Exception:
        return None


def convert_video(
    job: ConvertJob,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Optional[str]:
    """
    영상 → GIF/WebP/APNG 변환.

    Args:
        job: ConvertJob 설정
        on_progress: (percent 0~100, message) 콜백

    Returns:
        출력 파일 경로 또는 None
    """
    ff = find_ffmpeg()
    if not ff:
        if on_progress:
            on_progress(0, "❌ FFmpeg를 찾을 수 없습니다")
        return None

    if not Path(job.input_path).exists():
        if on_progress:
            on_progress(0, "❌ 입력 파일이 없습니다")
        return None

    # 영상 정보 가져오기 (진행률 계산용)
    vinfo = probe_video(job.input_path)
    total_duration = 0.0
    if vinfo:
        end = job.end_time if job.end_time > 0 else vinfo.duration
        start = job.start_time
        total_duration = max(0.1, (end - start) / max(0.01, job.speed))

    def progress(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    progress(0, "변환 준비 중...")

    if job.output_format == "gif":
        return _convert_to_gif(ff, job, total_duration, progress)
    elif job.output_format == "webp":
        return _convert_to_webp(ff, job, total_duration, progress)
    elif job.output_format == "apng":
        return _convert_to_apng(ff, job, total_duration, progress)
    elif job.output_format == "mp4":
        return _convert_to_mp4(ff, job, total_duration, progress)
    else:
        return _convert_to_gif(ff, job, total_duration, progress)


def _build_input_args(job: ConvertJob) -> list:
    """입력 관련 FFmpeg 인수 생성"""
    args = []

    # 시작 시간
    if job.start_time > 0:
        args += ["-ss", f"{job.start_time:.3f}"]

    args += ["-i", job.input_path]

    # 종료 시간
    if job.end_time > 0:
        duration = job.end_time - job.start_time
        args += ["-t", f"{duration:.3f}"]

    return args


def _escape_drawtext(text: str) -> str:
    """FFmpeg drawtext 필터용 문자 이스케이프"""
    # 콜론, 백슬래시, 작은따옴표, 퍼센트 이스케이프
    text = text.replace('\\', '\\\\')
    text = text.replace(':', '\\:')
    text = text.replace("'", "\\'")
    text = text.replace('%', '\\%')
    return text


def _build_subtitle_filters(subtitles: list, job_start: float = 0.0,
                            output_height: int = 480) -> str:
    """
    자막 리스트를 FFmpeg drawtext 필터 체인으로 변환.
    줄바꿈 지원: 여러 줄은 각각 별도 drawtext로 처리.
    fontsize는 480p 기준 → 출력 해상도에 비례 조정.
    """
    if not subtitles:
        return ""

    # 480p 기준으로 정규화 (사용자가 설정한 크기는 480p 기준)
    size_scale = output_height / 480.0

    filters = []
    for sub in subtitles:
        if not sub.text.strip():
            continue

        # 잘린 구간 기준으로 시간 조정
        rel_start = max(0, sub.start - job_start)
        rel_end = max(0, sub.end - job_start)

        if rel_end <= rel_start:
            continue

        # 한글 폰트 (Bold / Regular)
        bold = getattr(sub, 'bold', True)
        if bold:
            font_part = "fontfile='C\\:/Windows/Fonts/malgunbd.ttf'"
        else:
            font_part = "fontfile='C\\:/Windows/Fonts/malgun.ttf'"

        # 색상
        color = sub.color.replace('#', '0x') if sub.color.startswith('#') else sub.color

        # 출력 해상도에 맞게 폰트 크기 조정
        actual_fontsize = max(12, int(sub.size * size_scale))
        line_height = actual_fontsize + 8
        border_w = max(1, int(2 * size_scale))
        box_border = max(4, int(8 * size_scale))

        # 줄바꿈 처리
        lines = sub.text.split("\n")
        total_lines = len(lines)

        for line_idx, line_text in enumerate(lines):
            line_text = line_text.strip()
            if not line_text:
                continue

            text_escaped = _escape_drawtext(line_text)

            if sub.position == "top":
                base_y = f"h*0.05"
                y = f"{base_y}+{line_idx * line_height}"
            elif sub.position == "middle":
                total_h = total_lines * line_height
                offset = line_idx * line_height - total_h // 2
                y = f"(h/2)+{offset}"
            else:  # bottom
                reverse_idx = total_lines - 1 - line_idx
                y = f"h-{(reverse_idx + 1) * line_height}-h*0.05"

            filt = (
                f"drawtext=text='{text_escaped}':"
                f"{font_part}:"
                f"fontsize={actual_fontsize}:"
                f"fontcolor={color}:"
                f"borderw={border_w}:bordercolor=black:"
                f"box=1:boxcolor=black@0.5:boxborderw={box_border}:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{rel_start:.3f},{rel_end:.3f})'"
            )
            filters.append(filt)

    return ",".join(filters)


def _build_filter(job: ConvertJob, for_gif: bool = False) -> str:
    """FFmpeg 필터 체인 생성"""
    filters = []

    # 속도 조절
    if job.speed != 1.0:
        filters.append(f"setpts={1.0/job.speed}*PTS")

    # FPS
    filters.append(f"fps={job.fps}")

    # 리사이즈
    if job.width > 0:
        h = job.height if job.height > 0 else -1
        filters.append(f"scale={job.width}:{h}:flags=lanczos")

    # GIF 팔레트 최적화
    if for_gif:
        filters.append("split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5")

    return ",".join(filters) if not for_gif else ";".join([",".join(filters[:-1]), filters[-1]]) if len(filters) > 1 else filters[0]


def _convert_to_gif(
    ff: str,
    job: ConvertJob,
    total_duration: float,
    progress: Callable,
) -> Optional[str]:
    """GIF 변환 (진짜 2-pass: 팔레트 임시 파일 사용 → 메모리 절약)"""
    import os

    progress(5, "팔레트 생성 중 (1/2)...")

    # 필터 구성 (공통)
    filter_parts = []
    if job.speed != 1.0:
        filter_parts.append(f"setpts={1.0/max(0.01, job.speed)}*PTS")
    filter_parts.append(f"fps={job.fps}")
    if job.width > 0:
        h = job.height if job.height > 0 else -1
        filter_parts.append(f"scale={job.width}:{h}:flags=lanczos")

    # 자막 필터 추가
    sub_filter = _build_subtitle_filters(job.subtitles, job.start_time, job.output_height)
    if sub_filter:
        filter_parts.append(sub_filter)
    try:
        from watermark import drawtext_filter
        _wm_f = drawtext_filter(job.output_height or 480)
        if _wm_f:
            filter_parts.append(_wm_f)
    except Exception:
        pass

    base_filter = ",".join(filter_parts)

    # ── 구간 옵션 분리 ──
    # -ss는 입력 앞에, -t는 출력 쪽에 별도로 적용 (두 입력 사이에 놓으면 무시됨!)
    ss_args = []
    if job.start_time > 0:
        ss_args = ["-ss", f"{job.start_time:.3f}"]

    t_args = []
    if job.end_time > 0:
        duration = job.end_time - job.start_time
        t_args = ["-t", f"{duration:.3f}"]

    # ── 1st Pass: 팔레트 생성 (입력 1개라 기존 방식 OK) ──
    palette_path = tempfile.mktemp(suffix='_palette.png')
    pass1_args = (
        ss_args +
        ["-i", job.input_path] +
        t_args +
        ["-vf", f"{base_filter},palettegen=max_colors=256:stats_mode=diff",
         "-y", palette_path]
    )

    try:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": 300}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        r1 = subprocess.run([ff, "-y"] + pass1_args, **kwargs)
        if r1.returncode != 0 or not os.path.exists(palette_path):
            err = r1.stderr.decode('utf-8', errors='replace')[-200:]
            progress(0, f"❌ 팔레트 생성 실패: {err.strip()}")
            return None

        if job.cancelled:
            try:
                os.unlink(palette_path)
            except Exception:
                pass
            return None

        progress(50, "GIF 생성 중 (2/2)...")

        # ── 2nd Pass: 두 입력 사용, -t는 출력 측으로 이동 ──
        # ffmpeg -ss 1 -i video.mp4 -i palette.png -t 3 -lavfi "..." -y out.gif
        pass2_args = (
            ss_args +
            ["-i", job.input_path,
             "-i", palette_path] +
            t_args +  # ← 두 입력 뒤, 출력 옵션 앞에 배치 (출력에 적용됨)
            ["-lavfi", f"{base_filter} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
             "-loop", str(job.loop),
             "-y", job.output_path]
        )

        result = _run_ffmpeg_with_progress(ff, pass2_args, total_duration, progress, job)

        # 팔레트 임시 파일 정리
        try:
            os.unlink(palette_path)
        except Exception:
            pass

        return result

    except subprocess.TimeoutExpired:
        progress(0, "❌ 팔레트 생성 시간 초과")
        try:
            os.unlink(palette_path)
        except Exception:
            pass
        return None
    except Exception as e:
        progress(0, f"❌ GIF 변환 오류: {e}")
        try:
            os.unlink(palette_path)
        except Exception:
            pass
        return None


def _convert_to_webp(
    ff: str,
    job: ConvertJob,
    total_duration: float,
    progress: Callable,
) -> Optional[str]:
    """WebP 애니메이션 변환"""
    progress(5, "WebP 변환 중...")

    filter_parts = []
    if job.speed != 1.0:
        filter_parts.append(f"setpts={1.0/max(0.01, job.speed)}*PTS")
    filter_parts.append(f"fps={job.fps}")
    if job.width > 0:
        h = job.height if job.height > 0 else -1
        filter_parts.append(f"scale={job.width}:{h}:flags=lanczos")

    # 자막 필터 추가
    sub_filter = _build_subtitle_filters(job.subtitles, job.start_time, job.output_height)
    if sub_filter:
        filter_parts.append(sub_filter)
    try:
        from watermark import drawtext_filter
        _wm_f = drawtext_filter(job.output_height or 480)
        if _wm_f:
            filter_parts.append(_wm_f)
    except Exception:
        pass

    vf = ",".join(filter_parts)

    # WebP 애니메이션 생성을 위한 올바른 args:
    # - libwebp 코덱 + -loop 으로 애니메이션 지정
    # - compression_level 1 (빠름)
    # - -threads 0 (멀티 스레드)
    args = _build_input_args(job) + [
        "-vf", vf,
        "-c:v", "libwebp",
        "-lossless", "0",
        "-compression_level", "1",
        "-quality", str(job.quality),
        "-loop", str(job.loop),
        "-preset", "picture",
        "-threads", "0",
        "-an",
        "-f", "webp",
        "-y", job.output_path,
    ]

    return _run_ffmpeg_with_progress(ff, args, total_duration, progress, job)


def _convert_to_apng(
    ff: str,
    job: ConvertJob,
    total_duration: float,
    progress: Callable,
) -> Optional[str]:
    """APNG 변환"""
    progress(5, "APNG 변환 중...")

    filter_parts = []
    if job.speed != 1.0:
        filter_parts.append(f"setpts={1.0/max(0.01, job.speed)}*PTS")
    filter_parts.append(f"fps={job.fps}")
    if job.width > 0:
        h = job.height if job.height > 0 else -1
        filter_parts.append(f"scale={job.width}:{h}:flags=lanczos")

    # 자막 필터 추가
    sub_filter = _build_subtitle_filters(job.subtitles, job.start_time, job.output_height)
    if sub_filter:
        filter_parts.append(sub_filter)
    try:
        from watermark import drawtext_filter
        _wm_f = drawtext_filter(job.output_height or 480)
        if _wm_f:
            filter_parts.append(_wm_f)
    except Exception:
        pass

    vf = ",".join(filter_parts)

    plays = 0 if job.loop == 0 else job.loop
    args = _build_input_args(job) + [
        "-vf", vf,
        "-plays", str(plays),
        "-an",
        "-f", "apng",
        "-y", job.output_path,
    ]

    return _run_ffmpeg_with_progress(ff, args, total_duration, progress, job)


def _convert_to_mp4(
    ff: str,
    job: ConvertJob,
    total_duration: float,
    progress: Callable,
) -> Optional[str]:
    """
    MP4(H.264 + AAC) 변환. 원본 오디오 유지.
    shorts_vertical=True 면 9:16 세로 캔버스(1080×1920)에 블러 배경으로 맞춘다.
    """
    progress(5, "MP4 변환 중...")

    speed = max(0.01, job.speed)
    shorts = getattr(job, "shorts_vertical", False)

    # 오디오 유무 확인
    vinfo = probe_video(job.input_path)
    has_audio = bool(vinfo and vinfo.has_audio)

    # 품질(10~100) → CRF(약 18~32, 낮을수록 고화질)
    q = max(10, min(100, job.quality))
    crf = int(round(18 + (100 - q) * 0.16))

    # 구간 옵션 (-ss 입력 앞, -t 입력 뒤)
    ss_args = ["-ss", f"{job.start_time:.3f}"] if job.start_time > 0 else []
    t_args = []
    if job.end_time > 0:
        t_args = ["-t", f"{(job.end_time - job.start_time):.3f}"]

    # 비디오 전처리(속도/FPS)
    pre = []
    if speed != 1.0:
        pre.append(f"setpts={1.0 / speed}*PTS")
    pre.append(f"fps={job.fps}")
    pre_str = ",".join(pre)

    # 자막 (쇼츠면 1920 높이 기준 정규화)
    out_h = 1920 if shorts else (job.output_height or 480)
    sub_filter = _build_subtitle_filters(job.subtitles, job.start_time, out_h)
    try:
        from watermark import drawtext_filter
        wm_filter = drawtext_filter(out_h)
    except Exception:
        wm_filter = ""
    overlay_filter = ",".join([x for x in (sub_filter, wm_filter) if x])

    # 비디오 필터/맵 구성
    if shorts:
        TW, TH = 1080, 1920
        fc = (
            f"[0:v]{pre_str},split=2[bg][fg];"
            f"[bg]scale={TW}:{TH}:force_original_aspect_ratio=increase,"
            f"crop={TW}:{TH},boxblur=20:2[bgb];"
            f"[fg]scale={TW}:{TH}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[vmid]"
        )
        vlabel = "[vmid]"
        if overlay_filter:
            fc += f";[vmid]{overlay_filter}[vout]"
            vlabel = "[vout]"
        video_args = ["-filter_complex", fc, "-map", vlabel]
    else:
        vf = list(pre)
        if job.width > 0:
            h = job.height if job.height > 0 else -2
            vf.append(f"scale={job.width}:{h}:flags=lanczos")
        else:
            # H.264는 짝수 해상도 필요
            vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        if overlay_filter:
            vf.append(overlay_filter)
        video_args = ["-vf", ",".join(vf), "-map", "0:v"]

    # 오디오 구성 (원본 유지 + 속도 변경 시 atempo)
    if has_audio:
        audio_args = ["-map", "0:a?", "-c:a", "aac", "-b:a", "128k"]
        if speed != 1.0:
            audio_args += ["-af", f"atempo={speed:.4f}"]
    else:
        audio_args = ["-an"]

    args = (
        ss_args
        + ["-i", job.input_path]
        + t_args
        + video_args
        + audio_args
        + [
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(crf),
            "-preset", "veryfast",
            "-movflags", "+faststart",
            "-y", job.output_path,
        ]
    )

    return _run_ffmpeg_with_progress(ff, args, total_duration, progress, job)


def _run_ffmpeg_with_progress(
    ff: str,
    args: list,
    total_duration: float,
    progress: Callable,
    job: ConvertJob,
) -> Optional[str]:
    """FFmpeg 실행 + stderr 파싱으로 실시간 진행률"""
    cmd = [ff] + ["-progress", "pipe:1"] + args

    try:
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        proc = subprocess.Popen(cmd, **kwargs)

        # stderr를 별도 스레드에서 비우기 (버퍼 막힘 방지)
        import threading as _th
        def _drain_stderr():
            try:
                while True:
                    chunk = proc.stderr.read(4096)
                    if not chunk:
                        break
            except Exception:
                pass
        stderr_thread = _th.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # stdout에서 progress 파싱 (heartbeat 포함)
        import time as _time
        last_pct = 5
        last_update = _time.time()
        start_time = _time.time()
        heartbeat_dots = 0

        while True:
            if job.cancelled:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
                progress(0, "⏹ 취소됨")
                return None

            # 30분 안전 타임아웃
            if _time.time() - start_time > 1800:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
                progress(0, "❌ 변환 시간 초과 (30분)")
                return None

            line = proc.stdout.readline()

            # heartbeat: readline이 비어있으면 (1초 쉬고) UI 업데이트
            if not line:
                if proc.poll() is not None:
                    break
                # 5초마다 heartbeat로 사용자에게 살아있음 알림
                if _time.time() - last_update > 5:
                    heartbeat_dots = (heartbeat_dots + 1) % 4
                    dots = "." * heartbeat_dots
                    progress(last_pct, f"변환 중 (대용량 인코딩){dots}")
                    last_update = _time.time()
                _time.sleep(0.1)
                continue

            line_str = line.decode('utf-8', errors='replace').strip()

            if line_str.startswith("out_time_us="):
                try:
                    us = int(line_str.split("=")[1])
                    current_sec = us / 1_000_000
                    if total_duration > 0:
                        pct = min(95, int(5 + (current_sec / total_duration) * 90))
                        if pct > last_pct:
                            last_pct = pct
                            progress(pct, f"변환 중... {pct}%")
                            last_update = _time.time()
                except ValueError:
                    pass

            elif line_str.startswith("progress=end"):
                break

        proc.wait(timeout=10)

        if proc.returncode == 0 and Path(job.output_path).exists():
            size = format_filesize(Path(job.output_path).stat().st_size)
            progress(100, f"✅ 완료! {size}")
            return job.output_path
        else:
            # stderr는 drain 스레드가 읽어갔음 — 이미 닫혔을 수 있음
            try:
                stderr_out = proc.stderr.read().decode('utf-8', errors='replace') if proc.stderr else ""
            except Exception:
                stderr_out = ""
            err_msg = stderr_out[-200:] if len(stderr_out) > 200 else stderr_out
            progress(0, f"❌ FFmpeg 오류: {err_msg.strip() or '알 수 없는 오류'}")
            return None

    except subprocess.TimeoutExpired:
        progress(0, "❌ 변환 시간 초과")
        return None
    except Exception as e:
        progress(0, f"❌ 변환 오류: {e}")
        return None


def estimate_video_output_size(
    vinfo: VideoInfo,
    output_format: str,
    fps: int,
    width: int,
    quality: int,
    start: float,
    end: float,
    speed: float,
) -> int:
    """대략적인 출력 용량 추정 (바이트)"""
    duration = ((end if end > 0 else vinfo.duration) - start) / max(0.1, speed)
    total_frames = int(duration * fps)
    w = width if width > 0 else vinfo.width
    ratio = w / max(1, vinfo.width)
    h = int(vinfo.height * ratio)
    pixels_per_frame = w * h

    if output_format == "gif":
        return int(total_frames * pixels_per_frame * 0.4)
    elif output_format == "webp":
        q_ratio = 0.03 + (quality / 100) * 0.2
        return int(total_frames * pixels_per_frame * q_ratio)
    elif output_format == "apng":
        return int(total_frames * pixels_per_frame * 1.2)
    elif output_format == "mp4":
        # H.264: 품질에 따라 대략 0.05~0.15 bytes/pixel
        q_ratio = 0.05 + (quality / 100) * 0.1
        return int(total_frames * pixels_per_frame * q_ratio)

    return int(total_frames * pixels_per_frame * 0.4)
