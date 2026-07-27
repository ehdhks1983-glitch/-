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
    # ⛑ 시간 순서가 뒤바뀐 구간(콜드오픈 티저 앞세우기 등)을 한 그래프로 처리하면
    # ffmpeg이 앞 구간을 내보내는 동안 뒤 구간 프레임을 전부 메모리에 쌓아
    # 긴 영상에서 'Cannot allocate memory'로 죽는다 (v0.81.1 사용자 리포트:
    # 149초 영상 + 첫 3초 티저). → 구간별 추출 후 합본하는 2단계로 우회.
    starts = [s for s, _ in segments]
    if any(b < a for a, b in zip(starts, starts[1:])):
        return _cut_reordered(video_path, segments, out_path, fps, transition)
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
    # 구간이 아주 많으면 명령줄 한계(Windows 32K) 회피 — 파일 경유(빌드별 옵션 자동 선택)
    args += ff.filter_complex_args(filtergraph, Path(out_path).with_suffix(".filter.txt"))
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


def _cut_reordered(video_path: str, segments: List[Tuple[int, int]], out_path: str,
                   fps: int = 30, transition: str = "none") -> str:
    """시간 역행 구간 컷 — 구간별로 따로 뽑아 파일 합본 (v0.81.1 메모리 안전).

    한 필터 그래프의 branch 재정렬은 긴 영상에서 프레임이 통째로 버퍼링돼 메모리
    부족을 일으키므로, 구간마다 입력 시킹(-ss)으로 조각 파일을 만든 뒤
    concat_videos로 잇는다. 조각은 crf16(저손실)으로 뽑아 이중 인코딩 손실 최소화.
    """
    out = Path(out_path)
    has_audio = ff.has_audio_stream(str(video_path))
    total_us = ff.probe_duration_us(str(video_path))
    fd = TRANSITION_FADE_S
    n = len(segments)
    tmps: List[str] = []     # 합본 입력 (순서 유지)
    made: List[str] = []     # 새로 만든 조각만 정리 대상 (원본은 지우면 안 됨)
    try:
        for i, (s, e) in enumerate(segments):
            # ⚡ 본편 전체(≈0~끝) 구간은 재추출 생략 — 원본을 그대로 합본 입력으로.
            # 콜드오픈(티저+전체)에서 긴 인코딩 1회가 통째로 줄어 몇 분 단축 (v0.81.2).
            # (이 구간의 0.14초 경계 페이드만 생략됨 — 체감 없음)
            if s <= 100_000 and e >= total_us - 100_000:
                tmps.append(str(video_path))
                continue
            piece = out.with_name(f"{out.stem}_seg{i:02d}.mp4")
            dur_s = max(0.05, (e - s) / 1e6)
            vf = "setpts=PTS-STARTPTS"
            if transition == "fade" and n > 1:
                if i > 0 and dur_s > fd * 2:
                    vf += f",fade=t=in:st=0:d={fd}"
                if i < n - 1 and dur_s > fd * 2:
                    vf += f",fade=t=out:st={max(0.0, dur_s - fd):.3f}:d={fd}"
            args = [ff.ffmpeg_bin(), "-y", "-v", "error",
                    "-ss", us_to_seconds_str(s), "-i", str(video_path),
                    "-t", f"{dur_s:.6f}", "-vf", vf,
                    "-r", str(fps), "-c:v", "libx264", "-crf", "16",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
            if has_audio:
                args += ["-c:a", "aac", "-b:a", "192k"]
            else:
                args += ["-an"]
            args += ["-movflags", "+faststart", str(piece)]
            ff.run(args)
            tmps.append(str(piece))
            made.append(str(piece))
        w, h = ff.probe_video_size(str(video_path))
        concat_videos(tmps, str(out), size=(w, h), fps=fps)
    finally:
        for t in made:
            try:
                Path(t).unlink()
            except OSError:
                pass
    return str(out)


def speed_video(video: str, factor: float, out_path: str, fps: int = 30) -> str:
    """영상만 배속한 무음 클립 (v0.82 구간 조립용 — 원본 소리는 어차피 내레이션이 대체).

    factor>1 빠르게, <1 느리게 (0.25~8배 클램프). 화질 저손실(crf16)·ultrafast.
    """
    factor = max(0.25, min(8.0, float(factor or 1.0)))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(video),
            "-vf", f"setpts=PTS/{factor:.6f}", "-an",
            "-r", str(fps), "-c:v", "libx264", "-crf", "16",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out_path)])
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


def photo_sentence_spans(n_images: int, sub_starts_us: List[int],
                         total_us: int) -> List[Tuple[int, int]]:
    """사진 ↔ 내레이션 문장 매핑 → [(사진 번호, 지속 μs)] (v0.79 사진-문장 싱크).

    문장 j 블록 = [j 시작, j+1 시작) — 첫 블록은 0부터, 마지막은 total_us까지.
    사진이 문장보다 많으면 앞쪽 문장 수만큼만 쓰고, 적으면 연속 블록을 묶어 커버.
    지속 합계는 항상 total_us (내레이션 길이와 영상 길이가 정확히 일치).
    """
    m = len(sub_starts_us)
    if n_images <= 0 or m == 0 or total_us <= 0:
        return []
    bounds = [0] + [max(0, int(s)) for s in sub_starts_us[1:]] + [int(total_us)]
    durs = [max(0, bounds[j + 1] - bounds[j]) for j in range(m)]
    n = min(n_images, m)
    spans: List[Tuple[int, int]] = []
    for i in range(n):
        lo, hi = i * m // n, (i + 1) * m // n
        d = sum(durs[lo:hi])
        if d > 0:
            spans.append((i, d))
    gap = int(total_us) - sum(d for _, d in spans)  # 경계 반올림·0블록 보정
    if spans and gap > 0:
        spans[-1] = (spans[-1][0], spans[-1][1] + gap)
    return spans


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
    # 사진이 아주 많으면(수백 장) 그래프가 명령줄 한계를 넘을 수 있어 파일 경유
    args += ff.filter_complex_args(fc, Path(out_path).with_suffix(".filter.txt"))
    args += ["-map", "[v]", "-map", f"{len(images)}:a",
             "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out_path)]
    ff.run(args)
    return str(out_path)


_SCENE_PTS = re.compile(r"pts_time:([0-9.]+)")


def detect_scene_changes(video: str, threshold: float = 0.35,
                         limit: int = 500) -> List[int]:
    """장면이 확 바뀌는 시각(μs) 목록 (v0.44 — 컷 경계를 장면에 맞추는 용도).

    ffmpeg select='gt(scene,th)' + metadata=print 로 장면 전환 프레임만 골라 파싱.
    인코딩 없이 디코드만 하므로 빠르다. 실패하면 빈 목록(호출측은 스냅 생략).
    """
    proc = ff.run([
        ff.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(video),
        "-vf", f"select='gt(scene,{threshold})',metadata=print",
        "-an", "-f", "null", "-",
    ])
    text = proc.stderr.decode("utf-8", "replace")
    times = sorted({int(float(m) * 1e6) for m in _SCENE_PTS.findall(text)})
    return times[:limit]


def _nearest_scene(t_us: int, scenes: List[int], max_shift_us: int):
    best = None
    for s in scenes:
        if abs(s - t_us) <= max_shift_us and (best is None or abs(s - t_us) < abs(best - t_us)):
            best = s
    return best


def shift_ranges_to_scenes(ranges: List[Tuple[int, int]], scenes: List[int],
                           duration_us: int, max_shift_us: int = 1_500_000) -> List[Tuple[int, int]]:
    """몽타주용 — 떨어져 있는 각 구간을 통째로 밀어 시작점을 장면 전환에 맞춘다.

    구간 길이는 유지(전체 목표 길이 보존), 영상 밖·이전 구간과 겹치면 스냅 포기.
    """
    out: List[Tuple[int, int]] = []
    for s, e in ranges:
        snap = _nearest_scene(s, scenes, max_shift_us)
        if snap is not None:
            ns, ne = snap, snap + (e - s)
            if 0 <= ns and ne <= duration_us and (not out or ns >= out[-1][1]):
                out.append((ns, ne))
                continue
        if out and s < out[-1][1]:  # 앞 구간이 밀려 겹치면 원래 위치 유지 불가 → 뒤로
            s2 = out[-1][1]
            out.append((s2, s2 + (e - s)) if s2 + (e - s) <= duration_us else (s2, duration_us))
        else:
            out.append((s, e))
    return [r for r in out if r[1] - r[0] > 200_000]


def snap_boundaries_to_scenes(ranges: List[Tuple[int, int]], scenes: List[int],
                              max_shift_us: int = 1_500_000,
                              min_len_us: int = 3_000_000) -> List[Tuple[int, int]]:
    """분할용 — 이어져 있는 구간들의 '경계'를 가장 가까운 장면 전환으로 옮긴다.

    (쇼츠 여러 개로 나눌 때 장면 중간에서 뚝 끊기지 않게.) 양 끝은 고정,
    옮겨서 어느 쪽이 min_len 미만이 되면 그 경계는 그대로 둔다.
    """
    if len(ranges) < 2:
        return list(ranges)
    out = [list(r) for r in ranges]
    for i in range(len(out) - 1):
        b = out[i][1]
        snap = _nearest_scene(b, scenes, max_shift_us)
        if snap is None:
            continue
        if snap - out[i][0] >= min_len_us and out[i + 1][1] - snap >= min_len_us:
            out[i][1] = snap
            out[i + 1][0] = snap
    return [tuple(r) for r in out]


def xfade_clamp(crossfade_s: float, durs_s: List[float]) -> float:
    """클립 길이에 맞춰 크로스페이드 길이를 안전하게 줄인다 (v0.83).

    가장 짧은 클립의 45%를 넘지 않게(양쪽 다 겹칠 여유), 최대 1초.
    0.05초 미만이면 0(하드컷) — 그보다 짧으면 어차피 안 보인다.
    """
    if crossfade_s <= 0 or len(durs_s) < 2:
        return 0.0
    fade = min(float(crossfade_s), min(durs_s) * 0.45, 1.0)
    return fade if fade >= 0.05 else 0.0


# 🎬 크로스페이드 전환 종류 (v0.85) — xfade 기본 세트(ffmpeg 4.3+)만 사용해 호환 보장
def pad_video(src: str, out_path: str, head_s: float = 0.0, tail_s: float = 0.0,
              fps: int = 30) -> str:
    """앞뒤에 정지 프레임+무음 패딩 — 크로스페이드가 말을 잡아먹지 않게 (v0.94).

    합본의 xfade/acrossfade는 경계 양쪽을 겹쳐 소모한다. 내레이션이 경계까지
    차 있으면 뒷구간 첫 마디는 볼륨이 0에서 차오르며 깎여 들리고 앞구간 끝
    마디도 잘릴 수 있다 (사용자 리포트 "합쳐지는 부분에 말도 끊어지고").
    겹칠 만큼을 미리 '정지 화면 + 무음'으로 덧대 페이드가 패딩만 먹게 한다.
    """
    if head_s <= 0 and tail_s <= 0:
        return str(src)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    vf = (f"tpad=start_duration={max(0.0, head_s):.3f}:start_mode=clone"
          f":stop_duration={max(0.0, tail_s):.3f}:stop_mode=clone,fps={fps}")
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-vf", vf]
    if ff.has_audio_stream(str(src)):
        af = []
        if head_s > 0:
            af.append(f"adelay={int(head_s * 1000)}:all=1")
        if tail_s > 0:
            af.append(f"apad=pad_dur={tail_s:.3f}")
        args += ["-af", ",".join(af), "-c:a", "aac", "-b:a", "192k"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-pix_fmt", "yuv420p", str(out_path)]
    ff.run(args)
    return str(out_path)


XFADE_POOL = ["dissolve", "slideleft", "circleopen", "wipeleft", "smoothleft", "radial"]


def concat_videos(clips: List[str], out_path: str, size=None,
                  fps: int = 30, still_s: float = 2.5,
                  crossfade_s: float = 0.0, transition: str = "fade") -> str:
    """여러 클립(영상/사진 혼합)을 순서대로 이어붙인다 (v0.80 구간 조립 공용).

    - 해상도가 제각각이어도 size(기본: 첫 영상 클립 크기)에 맞춰 축소+패딩.
    - 소리 있는 클립은 44100 스테레오로 통일, 사진·무음 클립은 무음 트랙을 깔아
      concat 오류를 막는다. 사진은 still_s초 정지 클립으로.
    - crossfade_s>0 (v0.83): 경계마다 화면은 디졸브(xfade), 소리는 겹침 페이드
      (acrossfade)로 부드럽게 — 하드컷 "뚝" 끊김 제거. 전체 길이는 경계당
      crossfade_s만큼 짧아진다.
    - N이 커서 필터 그래프가 길어지면 파일 경유(filter_complex_args).
    """
    clips = [str(c) for c in clips if (c or "").strip() and Path(str(c)).is_file()]
    if not clips:
        raise ValueError("이어붙일 클립이 없습니다")
    if size:
        w, h = int(size[0]) & ~1, int(size[1]) & ~1
    else:
        first_vid = next((c for c in clips
                          if Path(c).suffix.lower() not in IMAGE_EXTS), clips[0])
        w, h = ff.probe_video_size(first_vid)
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin"]
    parts, labels, aux, durs = [], [], [], []
    for i, clip in enumerate(clips):
        is_img = Path(clip).suffix.lower() in IMAGE_EXTS
        if is_img:
            args += ["-loop", "1", "-t", f"{still_s:.3f}", "-i", str(clip)]
        else:
            args += ["-i", str(clip)]
        durs.append(still_s if is_img else ff.probe_duration_us(clip) / 1e6)
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
    fade = xfade_clamp(crossfade_s, durs)
    if fade > 0:
        # 🎬 크로스페이드 체인 — 입력을 순서대로 소비하므로 긴 영상도 메모리 안전.
        # transition="varied" (v0.85): 경계마다 다른 전환을 돌아가며 써 다양하게.
        chain, vcur, t = [], "[v0]", durs[0]
        offs = [0.0]
        for i in range(1, len(clips)):
            off = max(0.0, t - fade)
            offs.append(off)
            tname = (XFADE_POOL[(i - 1) % len(XFADE_POOL)]
                     if transition == "varied" else (transition or "fade"))
            vn = f"[vx{i}]"
            chain.append(f"{vcur}[v{i}]xfade=transition={tname}:"
                         f"duration={fade:.3f}:offset={off:.3f}{vn}")
            vcur = vn
            t = off + durs[i]
        # 🔊 소리는 페이드 없이 그대로 이어붙임 (v0.99) — acrossfade가 뒷클립
        # 첫마디를 0볼륨에서 서서히 키워 '말이 끊겨' 들리던 문제의 종결.
        # 각 클립 소리를 다음 클립이 시작하는 지점까지만 쓰고(잘리는 건 화면
        # 겹침 구간의 무음 꼬리뿐) 무편집 concat — 볼륨 변화가 전혀 없어
        # 경계의 쉼이 문장 사이 쉼과 같은 리듬이 된다. (amix는 빌드에 따라
        # 균일 감쇠가 생겨 배제)
        acat = ""
        for i in range(len(clips)):
            seg = (offs[i + 1] - offs[i]) if i + 1 < len(clips) else durs[i]
            chain.append(f"[a{i}]atrim=0:{max(0.05, seg):.3f},"
                         f"asetpts=PTS-STARTPTS[ac{i}]")
            acat += f"[ac{i}]"
        chain.append(acat + f"concat=n={len(clips)}:v=0:a=1[a]")
        fc = ";".join(parts + chain)
        vmap, amap = vcur, "[a]"
    else:
        fc = (";".join(parts) + ";" + "".join(labels)
              + f"concat=n={len(clips)}:v=1:a=1[v][a]")
        vmap, amap = "[v]", "[a]"
    args += ff.filter_complex_args(fc, Path(out_path).with_suffix(".filter.txt"))
    args += ["-map", vmap, "-map", amap,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out_path)]
    ff.run(args)
    return str(out_path)


def mix_bgm(video: str, bgm: str, out_path: str, bgm_db: float = -16.0,
            duck: bool = True) -> str:
    """완성 영상에 BGM만 얹는다 — 영상은 재인코딩 없이 복사 (v0.83).

    합본 전체를 다시 인코딩하던 방식(화질 열화·용량 증가·느림) 대체.
    소리 레시피는 렌더 단계와 동일: 루프 + 페이드인/아웃 + (옵션) 목소리
    덕킹(sidechaincompress).
    """
    dur_s = ff.probe_duration_us(video) / 1e6
    gain = 10 ** (bgm_db / 20)
    fade_st = max(0.0, dur_s - 1.2)
    parts = []
    if ff.has_audio_stream(video):
        parts.append("[0:a]anull[abase]")
    else:
        parts.append(f"anullsrc=r=44100:cl=stereo:d={dur_s:.3f}[abase]")
    parts.append(
        f"[1:a]volume={gain:.4f},atrim=0:{dur_s:.3f},"
        f"afade=t=in:d=0.8,afade=t=out:st={fade_st:.3f}:d=1.2[abgm]")
    if duck:
        parts.append("[abase]asplit[vmain][vside]")
        parts.append("[abgm][vside]sidechaincompress="
                     "threshold=0.03:ratio=8:attack=20:release=300[abgmd]")
        parts.append("[vmain][abgmd]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        parts.append("[abase][abgm]amix=inputs=2:duration=first:normalize=0[a]")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(video),
            "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", ";".join(parts),
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(out_path)])
    return str(out_path)


def shrink_video(video: str, out_path: str, crf: int = 25, max_h: int = 1080) -> str:
    """📦 업로드용 용량 줄이기 (v0.83) — 화질 거의 그대로 파일 크기 대폭 축소.

    1080p 초과(4K 업스케일 등)는 1080p로 낮추고, 이하면 해상도 유지.
    카페·블로그 첨부 한도나 느린 회선 때문에 업로드가 안 될 때 쓴다.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(video),
            "-vf", f"scale=-2:'min({int(max_h)},ih)'",
            "-c:v", "libx264", "-crf", str(int(crf)),
            "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if ff.has_audio_stream(video):
        args += ["-c:a", "aac", "-b:a", "128k"]
    args += ["-movflags", "+faststart", str(out_path)]
    ff.run(args)
    return str(out_path)


def extract_segment(video: str, start_us: int, end_us: int, out_path: str,
                    fps: int = 30) -> str:
    """풀영상에서 한 구간을 저손실 추출 (v0.84 — 구간 대본 「풀영상 하나로」 입력).

    입력 시킹(-ss)이라 긴 영상 뒷부분도 빠르다. 소리는 뺀다 — 내레이션이 대체.
    """
    dur_s = max(0.05, (end_us - start_us) / 1e6)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-ss", us_to_seconds_str(start_us), "-i", str(video),
            "-t", f"{dur_s:.6f}", "-vf", "setpts=PTS-STARTPTS",
            "-r", str(fps), "-c:v", "libx264", "-crf", "16",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
            "-movflags", "+faststart", str(out_path)])
    return str(out_path)


def partition_by_weights(total_us: int, weights: List[float],
                         scenes_us: Optional[List[int]] = None,
                         min_seg_us: int = 1_000_000) -> List[Tuple[int, int]]:
    """전체 길이를 가중치 비율로 연속 분할 (v0.84 — 풀영상 구간 자동 제안).

    weights = 구간별 내레이션 분량(글자 수 등). 경계는 가까운 장면 전환점
    (scenes_us)이 이웃 구간의 30% 안에 있으면 그리로 스냅 — 화면이 바뀌는
    지점에서 잘리게. 항상 총 n개의 연속·단조 구간을 돌려준다.
    """
    n = max(1, len(weights or []))
    ws = [max(0.001, float(w)) for w in (weights or [1.0])]
    tot_w = sum(ws)
    step_min = max(200_000, min(min_seg_us, total_us // (2 * n) or 1))
    bounds: List[int] = []
    acc = 0.0
    for w in ws[:-1]:
        acc += w
        bounds.append(int(total_us * acc / tot_w))
    snapped: List[int] = []
    prev = 0
    for j, b in enumerate(bounds):
        nxt = bounds[j + 1] if j + 1 < len(bounds) else total_us
        if scenes_us:
            tol = int(min(b - prev, nxt - b) * 0.3)
            best = min(scenes_us, key=lambda s, bb=b: abs(s - bb))
            if abs(best - b) <= tol:
                b = int(best)
        b = max(prev + step_min, min(b, total_us - step_min))
        b = min(b, total_us)                     # 초단편 영상 방어 (테스트·극단값)
        snapped.append(b)
        prev = b
    edges = [0] + snapped + [total_us]
    return [(edges[k], max(edges[k], edges[k + 1])) for k in range(n)]


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
    return concat_videos([c for c in (intro, video, outro) if c], out_path,
                         size=(w, h), fps=fps, still_s=still_s)


def hook_intro_clip(video: str, hook_audio: str, out_path: str, ding: str = "",
                    gain_db: float = -13.0, tail_s: float = 0.35, fps: int = 30) -> str:
    """🎙 후킹 보이스 인트로 클립 (v0.75) — 본편 첫 프레임 + 훅 음성(+띠링).

    본편 첫 프레임(상단 제목이 이미 구워져 있음)을 살짝 줌인하며 훅 음성을
    들려준다 → '성우가 제목을 읽어주며 시작'하는 오프닝. attach_branding으로
    본편 앞에 붙여 쓴다. 훅 음성이 비정상적으로 길어도 6초에서 자른다.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = ff.probe_video_size(video)
    dur_s = ff.probe_duration_us(hook_audio) / 1e6 + max(0.0, tail_s)
    dur_s = max(1.0, min(dur_s, 6.0))
    frame = out.with_suffix(".frame.png")
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin", "-i", str(video),
            "-frames:v", "1", str(frame)])
    audio = str(hook_audio)
    if ding and Path(ding).is_file():  # 띠링을 훅 음성 머리에 살짝 (기존 효과음 재사용)
        from ..spec import Sfx  # noqa: PLC0415
        from . import sfx as sfx_mod  # noqa: PLC0415

        mixed = str(out.with_suffix(".voice.wav"))
        audio = sfx_mod.mix_sfx(
            audio, [Sfx(path=ding, start_us=80_000, gain_db=gain_db, name="ding")],
            mixed)
    # 정지 프레임 + 미세 줌인 (zoompan — 켄번즈와 같은 패턴, 1.5x 선업스케일로 떨림 방지)
    n = max(2, int(round(dur_s * fps)))
    pre_w, pre_h = (w * 3 // 2) & ~1, (h * 3 // 2) & ~1
    vf = (
        f"[0:v]scale={pre_w}:{pre_h}:flags=lanczos,"
        f"zoompan=z='min(1+0.06*on/{n},1.06)'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={n}:s={w}x{h}:fps={fps},format=yuv420p[v];"
        f"[1:a]apad=pad_dur={tail_s + 0.2:.2f},atrim=0:{dur_s:.3f},"
        f"aformat=channel_layouts=stereo,aresample=44100[a]"
    )
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin",
            "-i", str(frame), "-i", audio,
            "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{dur_s:.3f}", "-movflags", "+faststart", str(out)])
    return str(out)


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
