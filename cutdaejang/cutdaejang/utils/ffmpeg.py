"""FFmpeg/ffprobe 헬퍼 — 실측(ffprobe)·진행률·GPU 자동 감지 (기획안 §5.5).

바이너리 경로는 환경변수 ``CUTDAEJANG_FFMPEG``/``CUTDAEJANG_FFPROBE``로 재지정 가능
(배포 시 동봉된 libass 포함 빌드를 가리키기 위함).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from .timefmt import seconds_to_us


class FFmpegError(RuntimeError):
    """FFmpeg/ffprobe 실행 실패."""


def ffmpeg_bin() -> str:
    return _resolve("CUTDAEJANG_FFMPEG", "ffmpeg")


def ffprobe_bin() -> str:
    return _resolve("CUTDAEJANG_FFPROBE", "ffprobe")


def _resolve(env_key: str, default: str) -> str:
    path = os.environ.get(env_key) or default
    found = shutil.which(path)
    if not found:
        raise FFmpegError(
            f"{default} 실행 파일을 찾을 수 없습니다 (환경변수 {env_key} 또는 PATH 확인). "
            "배포본에는 libass 포함 FFmpeg가 동봉되어야 합니다 (기획안 §4)."
        )
    return found


def run(cmd: list, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    """서브프로세스 실행. 비정상 종료 시 stderr 꼬리를 담아 FFmpegError."""
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace")[-2000:]
        raise FFmpegError(f"명령 실패(rc={proc.returncode}): {' '.join(map(str, cmd[:8]))}…\n{tail}")
    return proc


def probe(path: str) -> dict:
    """ffprobe JSON (format + streams)."""
    proc = run(
        [
            ffprobe_bin(),
            "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height,sample_rate",
            "-of", "json",
            str(path),
        ]
    )
    return json.loads(proc.stdout.decode("utf-8"))


def probe_duration_us(path: str) -> int:
    """컨테이너 길이 실측 → μs 정수. 타임라인 계산은 반드시 이 실측값만 사용한다."""
    info = probe(path)
    dur = info.get("format", {}).get("duration")
    if dur is None:
        raise FFmpegError(f"길이를 읽을 수 없음: {path}")
    try:
        return seconds_to_us(float(dur))
    except (TypeError, ValueError) as e:  # 일부 컨테이너는 "N/A"를 줌
        raise FFmpegError(f"길이를 읽을 수 없음({dur!r}): {path}") from e


# 이보다 짧은 «무음»은 패딩이 아니라 파형의 자연스러운 시작점이다.
# (순수 사인파는 0에서 시작해 첫 몇 샘플이 조용하다 — 실측 22μs)
_EDGE_MIN_US = 10_000


def edge_silence_us(path: str, thresh: int = 96) -> tuple:
    """클립 **앞뒤에 붙어 있는 «완전 무음»** 길이 (μs, 앞·뒤).

    🔴 회원님 25차: "목소리는 잘 바꿔졌는데 조금씩 끊켜"
    파형을 재 보니 문장 사이에 **진폭 0인 정적이 0.41~0.46초** 들어 있었다.
    코드가 넣는 간격은 0.30초인데 왜 0.42초인가 —

        TTS 다듬기(`postprocess_clip`)가 클릭 방지·숨결 보호로 클립 앞뒤에
        50ms씩 붙인다(v0.46.1). 그걸 모르고 문장 사이에 300ms를 **더** 넣으니
        실제로 들리는 정적은 50+300+50 = **400ms**가 된다.

    그래서 «넣을 간격»을 정할 때 이미 붙어 있는 무음을 빼야 한다. 제공자마다
    패딩이 다를 수 있으니 설정값을 믿지 않고 **파형을 직접 잰다.**
    잴 수 없는 형식이면 (0, 0) — 예전과 똑같이 동작한다.
    """
    import array  # noqa: PLC0415
    import wave  # noqa: PLC0415

    try:
        with wave.open(str(path), "rb") as wf:
            if wf.getsampwidth() != 2:
                return (0, 0)
            n, sr, ch = wf.getnframes(), wf.getframerate(), wf.getnchannels()
            if n <= 0 or sr <= 0 or ch <= 0:
                return (0, 0)
            data = array.array("h")
            data.frombytes(wf.readframes(n))
    except (OSError, wave.Error, EOFError, ValueError):
        return (0, 0)
    if not data:
        return (0, 0)
    head = tail = 0
    for v in data:
        if abs(v) > thresh:
            break
        head += 1
    if head >= len(data):          # 통째로 무음인 클립
        return (0, 0)
    for v in reversed(data):
        if abs(v) > thresh:
            break
        tail += 1
    per = ch * sr
    lead, trail = int(head * 1_000_000 / per), int(tail * 1_000_000 / per)
    # 몇 샘플짜리는 패딩이 아니다 — 멀쩡한 간격을 괜히 갉아먹지 않게
    return (lead if lead >= _EDGE_MIN_US else 0,
            trail if trail >= _EDGE_MIN_US else 0)


def probe_video_size(path: str) -> tuple:
    for s in probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise FFmpegError(f"비디오 스트림 없음: {path}")


def has_audio_stream(path: str) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


_NVENC_CACHE: Optional[bool] = None


def nvenc_available() -> bool:
    """h264_nvenc 사용 가능 여부 — 인코더 목록 확인 후 0.1초 테스트 인코딩까지 통과해야 True.

    (드라이버 미설치 등으로 목록에는 있어도 실행이 실패하는 경우가 흔해 실인코딩으로 확정)
    """
    global _NVENC_CACHE
    if _NVENC_CACHE is not None:
        return _NVENC_CACHE
    try:
        listed = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
        )
        if b"h264_nvenc" not in listed.stdout:
            _NVENC_CACHE = False
            return False
        test = subprocess.run(
            [
                ffmpeg_bin(), "-hide_banner", "-v", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        _NVENC_CACHE = test.returncode == 0
    except Exception:
        _NVENC_CACHE = False
    return _NVENC_CACHE


_FILTER_INLINE_MAX = 20000  # Windows CreateProcess 한계(32767자)에 여유를 둔 인라인 상한
_FILTER_SCRIPT_OPT: dict = {}


def _filter_script_opt(bin_path: str) -> str:
    """이 빌드가 지원하는 「필터그래프를 파일로」 옵션 이름.

    FFmpeg 7.0부터 -filter_complex_script 가 -/filter_complex 로 대체(deprecated)됐고
    2025년 이후 master 빌드(BtbN 등 — 1_설치.bat이 받는 빌드)에서는 아예 제거되어
    "Unrecognized option"으로 즉사한다. 반대로 -/filter_complex 는 6.x 이하에 없다.
    → 도움말에서 구형 옵션 지원 여부를 1회 확인해 빌드별로 선택(캐시).
    """
    opt = _FILTER_SCRIPT_OPT.get(bin_path)
    if opt:
        return opt
    try:
        proc = subprocess.run(
            [bin_path, "-hide_banner", "-h", "full"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
        )
        if proc.returncode != 0 or not proc.stdout:
            legacy = True  # 도움말조차 못 내는 상태 — 감지 실패로 취급
        else:
            legacy = b"filter_complex_script" in proc.stdout
    except Exception:
        legacy = True  # 감지 실패 시 십수 년 지원돼 온 구형 옵션으로
    opt = "-filter_complex_script" if legacy else "-/filter_complex"
    _FILTER_SCRIPT_OPT[bin_path] = opt
    return opt


def filter_complex_args(graph: str, script_path) -> list:
    """-filter_complex 인자 목록. 짧으면 어느 빌드에서나 통하는 인라인, 길면 파일 경유.

    파일 경유 옵션은 빌드마다 다르므로(_filter_script_opt) 실행 파일에서 감지해 선택.
    """
    if len(graph) <= _FILTER_INLINE_MAX:
        return ["-filter_complex", graph]
    p = Path(script_path)
    p.write_text(graph, encoding="utf-8")
    return [_filter_script_opt(ffmpeg_bin()), str(p)]


def run_with_progress(
    args: list,
    total_us: int,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> None:
    """``-progress pipe:1`` 파싱으로 진행률 콜백(0.0~1.0) 호출 (기획안 §5.5-3 GUI 진행바용).

    args는 ffmpeg 바이너리를 제외한 인자 목록.

    ⚠ stderr를 반드시 별도 스레드로 동시에 비워야 한다. stdout만 읽으면서 stderr를
    방치하면, ffmpeg가 경고(libass 폰트 로딩 등)로 OS 파이프 버퍼를 채웠을 때 write에서
    블록되고 → stdout 진행률도 멈춰 → 렌더가 0%에서 영구 정지한다(Windows 버퍼가 작아
    특히 취약). `-loglevel error`로 stderr 양도 최소화한다.
    """
    import threading  # noqa: PLC0415

    cmd = [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats",
        "-progress", "pipe:1", *map(str, args),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None and proc.stderr is not None

    stderr_tail: deque = deque(maxlen=64)  # 마지막 64줄만 유지 (오류 리포트용)

    def drain_stderr() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            stderr_tail.append(line)

    err_thread = threading.Thread(target=drain_stderr, daemon=True)
    err_thread.start()

    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").strip()
        # out_time_ms는 이름과 달리 값이 µs인 빌드가 있어 동일 취급 (out_time_us 없는 구빌드 폴백)
        if progress_cb and line.startswith(("out_time_us=", "out_time_ms=")) and total_us > 0:
            try:
                progress_cb(min(1.0, int(line.split("=", 1)[1]) / total_us))
            except (ValueError, Exception):  # 콜백 예외로 ffmpeg가 고아가 되지 않게
                pass
        elif progress_cb and line == "progress=end":
            try:
                progress_cb(1.0)
            except Exception:  # noqa: BLE001
                pass

    proc.wait()
    err_thread.join(timeout=5)
    if proc.returncode != 0:
        tail = b"".join(stderr_tail).decode("utf-8", "replace")[-2000:]
        raise FFmpegError(f"렌더 실패(rc={proc.returncode}):\n{tail}")


def escape_filter_value(value: str) -> str:
    """필터 옵션 값(파일 경로 등)의 FFmpeg 필터그래프용 2단계 이스케이프.

    FFmpeg는 필터 인자를 두 번 파싱한다: ①그래프 파서가 홑따옴표를 벗겨내고
    ②옵션 파서가 콜론에서 key=value를 쪼갠다. 따라서 따옴표만으로는 Windows
    드라이브 콜론(C:)이 보호되지 않아 ``\\:`` 로 별도 이스케이프해야 한다
    (실기 검증: 미이스케이프 시 "No option name near ..." 오류).
    예) C:\\a b\\s.ass → 'C\\:/a b/s.ass'
    """
    v = value.replace("\\", "/")
    v = v.replace(":", "\\:")  # ② 옵션 파서용 — 따옴표가 벗겨진 뒤에도 콜론 보호
    return "'" + v.replace("'", r"'\''") + "'"  # ① 그래프 파서용
