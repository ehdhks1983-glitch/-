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
from ..utils.timefmt import seconds_to_us, us_to_seconds_str


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


TRANSITION_FADE_S = 0.14  # 구간 경계 페이드 길이 (짧은 dip — 길이 불변, 자막 싱크 유지)


def cut_and_concat(
    video_path: str, segments: List[Tuple[int, int]], out_path: str, fps: int = 30,
    transition: str = "none",
) -> str:
    """발화 구간만 잘라 이어붙인 영상 생성. trim+concat 재인코딩.

    오디오 트랙이 없는 영상(마이크 없는 화면 녹화)은 영상만 잘라 붙인다 —
    이후 렌더 단계가 무음 트랙을 알아서 붙이므로 결과는 동일.

    transition="fade" (v0.43): 구간 경계마다 화면만 살짝 어두워졌다 밝아지는 페이드.
    각 구간 안에서 fade in/out 하므로 전체 길이가 변하지 않아 자막 싱크가 유지된다.
    소리는 건드리지 않는다(말이 끊겨 들리지 않게). 영상 처음·끝에는 넣지 않는다.
    """
    if not segments:
        raise ValueError("자를 발화 구간이 없습니다")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    has_audio = ff.has_audio_stream(str(video_path))

    parts = []
    labels = []
    fd = TRANSITION_FADE_S
    for i, (s, e) in enumerate(segments):
        ss, se = us_to_seconds_str(s), us_to_seconds_str(e)
        vchain = f"[0:v]trim=start={ss}:end={se},setpts=PTS-STARTPTS"
        if transition == "fade" and len(segments) > 1:
            dur_s = (e - s) / 1e6
            if i > 0 and dur_s > fd * 2:
                vchain += f",fade=t=in:st=0:d={fd}"
            if i < len(segments) - 1 and dur_s > fd * 2:
                vchain += f",fade=t=out:st={max(0.0, dur_s - fd):.3f}:d={fd}"
        seg = vchain + f"[v{i}]"
        if has_audio:
            seg += f";[0:a]atrim=start={ss}:end={se},asetpts=PTS-STARTPTS[a{i}]"
        parts.append(seg)
        labels.append(f"[v{i}][a{i}]" if has_audio else f"[v{i}]")
    av = "v=1:a=1[v][a]" if has_audio else "v=1:a=0[v]"
    concat = "".join(labels) + f"concat=n={len(segments)}:{av}"
    filtergraph = ";".join(parts) + ";" + concat

    # 중간 산출물(최종 렌더에서 다시 인코딩됨) → ultrafast + 저손실 crf18로 속도 우선
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(video_path)]
    if len(segments) > 60:  # 구간이 아주 많으면 명령줄 길이 한계(Windows 32K) 회피
        script = Path(out_path).with_suffix(".filter.txt")
        script.write_text(filtergraph, encoding="utf-8")
        args += ["-filter_complex_script", str(script)]
    else:
        args += ["-filter_complex", filtergraph]
    args += ["-map", "[v]"]
    if has_audio:
        args += ["-map", "[a]"]
    args += [
        "-r", str(fps),
        "-c:v", "libx264", "-crf", "18", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        args += ["-c:a", "aac", "-b:a", "192k"]
    args += ["-movflags", "+faststart", str(out_path)]
    ff.run(args)
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


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def resolve_photo_inputs(path_str: str) -> List[str]:
    """사진 입력 해석 — 폴더(안의 사진 전부, 이름순) 또는 줄바꿈/세미콜론 구분 파일들."""
    raw = (path_str or "").replace(";", "\n").splitlines()
    out: List[str] = []
    for item in raw:
        p = Path(item.strip().strip('"'))
        if not str(p).strip():
            continue
        if p.is_dir():
            def natkey(f):
                # 1.jpg, 2.jpg, …, 10.jpg 가 숫자순이 되게 (사전식이면 1,10,2 순서가 됨)
                return [int(tok) if tok.isdigit() else tok.lower()
                        for tok in re.split(r"(\d+)", f.name)]
            out += [str(f) for f in sorted(p.iterdir(), key=natkey)
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        elif p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            out.append(str(p))
        else:
            raise ValueError(f"사진 파일/폴더를 찾을 수 없습니다: {p}")
    if not out:
        raise ValueError("사진이 없습니다 — 폴더에 jpg/png 사진을 넣거나 파일 경로를 확인하세요")
    return out


def photos_to_video(images: List[str], total_us: int, out_path: str,
                    size: Tuple[int, int] = (1080, 1920), fps: int = 30,
                    transition: str = "none") -> str:
    """사진들 → 슬라이드쇼 영상. 전체 길이를 장수로 균등 분배 (5장·15초 → 장당 3초).

    각 사진은 블러 배경 + 원본 비율 유지로 세로 캔버스에 배치(가로 사진도 자연스럽게).
    오디오는 무음 트랙(뒤에서 내레이션·BGM을 얹기 좋게).
    transition="fade" (v0.43): 사진이 바뀔 때 살짝 어두워졌다 밝아지는 전환 (길이 불변).
    """
    if not images:
        raise ValueError("사진이 없습니다")
    total_s_req = total_us / 1e6
    min_per = 0.35  # 장당 최소 표시 시간 — 이보다 짧으면 눈에 안 들어옴
    max_photos = max(1, int(total_s_req / min_per))
    if len(images) > max_photos:  # 전체 길이 약속을 지키기 위해 고르게 추림
        step = len(images) / max_photos
        picked = [images[int(i * step)] for i in range(max_photos)]
        import logging  # noqa: PLC0415
        logging.getLogger("cutdaejang").warning(
            "사진 %d장은 %d초에 다 못 담아 %d장만 고르게 사용합니다",
            len(images), int(total_s_req), len(picked))
        images = picked
    w, h = size
    per_s = total_s_req / len(images)
    fd = min(0.3, per_s / 4)  # 사진 전환 페이드 — 장당 시간이 짧으면 비례 축소
    args = [ff.ffmpeg_bin(), "-y", "-v", "error"]
    parts = []
    for i, img in enumerate(images):
        args += ["-loop", "1", "-t", f"{per_s:.3f}", "-i", str(img)]
        chain = (
            f"[{i}:v]split=2[bg{i}][fg{i}];"
            f"[bg{i}]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=24:2,eq=brightness=-0.1[bgb{i}];"
            f"[fg{i}]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs{i}];"
            f"[bgb{i}][fgs{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps}"
        )
        if transition == "fade" and len(images) > 1:
            if i > 0:
                chain += f",fade=t=in:st=0:d={fd:.3f}"
            if i < len(images) - 1:
                chain += f",fade=t=out:st={max(0.0, per_s - fd):.3f}:d={fd:.3f}"
        parts.append(chain + f"[v{i}]")
    total_s = per_s * len(images)
    args += ["-f", "lavfi", "-t", f"{total_s:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    fc = (";".join(parts) + ";"
          + "".join(f"[v{i}]" for i in range(len(images)))
          + f"concat=n={len(images)}:v=1:a=0[v]")
    args += ["-filter_complex", fc, "-map", "[v]", "-map", f"{len(images)}:a",
             "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out_path)]
    ff.run(args)
    return str(out_path)


def attach_branding(video: str, intro: str, outro: str, out_path: str,
                    fps: int = 30, still_s: float = 2.5) -> str:
    """본편 앞뒤에 인트로/아웃트로를 붙인다 (v0.43 채널 브랜딩).

    - intro/outro: 영상 파일 또는 사진(png/jpg — still_s초 정지 클립으로).
      빈 문자열/없는 파일은 조용히 건너뛰고, 둘 다 없으면 원본 경로를 그대로 반환.
    - 해상도가 달라도 본편 크기에 맞춰 축소 + 패딩(검정)으로 안전하게 이어붙인다.
    - 소리: 소리 있는 클립은 그대로, 없는 클립은 무음 트랙을 깔아 concat 오류 방지.
    """
    def _ok(p: str) -> bool:
        return bool((p or "").strip()) and Path(p.strip().strip('"')).is_file()

    intro = intro.strip().strip('"') if _ok(intro) else ""
    outro = outro.strip().strip('"') if _ok(outro) else ""
    if not intro and not outro:
        return video
    w, h = ff.probe_video_size(video)
    clips = [c for c in (intro, video, outro) if c]
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin"]
    parts, labels, aux = [], [], []
    for i, clip in enumerate(clips):
        is_img = Path(clip).suffix.lower() in IMAGE_EXTS
        if is_img:
            args += ["-loop", "1", "-t", f"{still_s:.3f}", "-i", str(clip)]
        else:
            args += ["-i", str(clip)]
        parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{i}]"
        )
        if not is_img and ff.has_audio_stream(clip):
            parts.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}]")
        else:  # 사진·무음 클립 → 그 길이만큼 무음 트랙
            dur_s = still_s if is_img else ff.probe_duration_us(clip) / 1e6
            aux.append((len(clips) + len(aux), dur_s))
            parts.append(
                f"[{aux[-1][0]}:a]atrim=duration={dur_s:.3f},"
                f"aformat=channel_layouts=stereo[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    for _idx, _dur in aux:
        args += ["-f", "lavfi", "-t", f"{_dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    fc = (";".join(parts) + ";" + "".join(labels)
          + f"concat=n={len(clips)}:v=1:a=1[v][a]")
    args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out_path)]
    ff.run(args)
    return str(out_path)


def extend_video(video: str, target_us: int, out_path: str, mode: str = "freeze") -> str:
    """영상을 target_us 길이까지 연장 (v0.42 — 내레이션이 영상보다 길 때).

    mode="freeze": 마지막 프레임을 정지 화면으로 이어붙임 (tpad clone)
    mode="loop":   영상을 처음부터 반복 재생해 채움
    이미 충분히 길면 원본 경로를 그대로 반환. 오디오는 무음 패딩/반복.
    """
    cur = ff.probe_duration_us(video)
    if target_us <= cur + 50_000:
        return video
    target_s = target_us / 1e6
    has_a = ff.has_audio_stream(video)
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if mode == "loop":
        loops = int(target_us // max(cur, 1)) + 1
        cmd = [ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin",
               "-stream_loop", str(loops), "-i", str(video),
               "-t", f"{target_s:.3f}", *enc]
        cmd += (["-c:a", "aac", "-b:a", "192k"] if has_a else ["-an"])
    else:  # freeze
        extra_s = (target_us - cur) / 1e6 + 0.2  # tpad 오차 여유 (뒤에서 -t로 정확히 자름)
        cmd = [ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin", "-i", str(video),
               "-vf", f"tpad=stop_mode=clone:stop_duration={extra_s:.3f}", *enc]
        if has_a:
            cmd += ["-af", f"apad=pad_dur={extra_s:.3f}", "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-an"]
        cmd += ["-t", f"{target_s:.3f}"]
    cmd.append(str(out_path))
    ff.run(cmd)
    return str(out_path)
