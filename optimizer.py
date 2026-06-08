"""
optimizer.py - 용량 최적화
GIF: gifsicle lossy → Pillow 색상 감소 폴백
WebP: 품질 점진 하락
목표 용량 맞추기
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Callable

from PIL import Image


# ─── gifsicle 감지 ───
_gifsicle_path: Optional[str] = None


def find_gifsicle() -> Optional[str]:
    """gifsicle 바이너리 경로 (내장 → 시스템 PATH)"""
    global _gifsicle_path
    if _gifsicle_path:
        return _gifsicle_path

    # 내장 (EXE 빌드 시 같이 배포)
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent

    for name in ("gifsicle.exe", "gifsicle"):
        local = base / name
        if local.exists():
            _gifsicle_path = str(local)
            return _gifsicle_path
        local2 = base / "tools" / name
        if local2.exists():
            _gifsicle_path = str(local2)
            return _gifsicle_path

    # 시스템 PATH
    found = shutil.which("gifsicle")
    if found:
        _gifsicle_path = found
        return _gifsicle_path

    return None


def gifsicle_available() -> bool:
    return find_gifsicle() is not None


def polish_gif(
    path: str,
    lossy: int = 30,
    on_progress: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    목표 용량과 무관하게 gifsicle로 가볍게 무손실급 압축(--lossy + -O3).
    결과가 더 작을 때만 제자리(in-place) 교체. gifsicle 없거나 실패하면 원본 유지(False).
    화질 프리셋의 '균형/빠른로딩'에서 로딩 단축용으로 항상 호출됨.
    """
    gs = find_gifsicle()
    if not gs or lossy <= 0:
        return False

    out = Path(tempfile.mktemp(suffix='.gif'))
    cmd = [gs, f"--lossy={lossy}", "--optimize=3", "--no-warnings", "-o", str(out), path]
    try:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": 180}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        subprocess.run(cmd, **kwargs)

        if (out.exists() and out.stat().st_size > 0
                and out.stat().st_size < Path(path).stat().st_size):
            shutil.move(str(out), path)
            if on_progress:
                on_progress(f"gifsicle lossy={lossy} → {Path(path).stat().st_size // 1024}KB")
            return True
        out.unlink(missing_ok=True)
    except Exception:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
    return False


# ─── gifsicle lossy 최적화 ───
def _optimize_gif_gifsicle(
    input_path: str,
    target_size_kb: int,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    gifsicle --lossy 로 GIF 용량 줄이기.
    lossy 값을 20 → 40 → 60 → 80 → 120 → 200 올려가며 목표 도달.
    """
    gs = find_gifsicle()
    if not gs:
        return None

    target_bytes = target_size_kb * 1024

    for lossy_val in (20, 40, 60, 80, 120, 200):
        out = Path(tempfile.mktemp(suffix='.gif'))
        cmd = [
            gs,
            "--lossy=" + str(lossy_val),
            "--optimize=3",
            "--no-warnings",
            "-o", str(out),
            input_path,
        ]

        try:
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": 120}
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = si

            subprocess.run(cmd, **kwargs)

            if out.exists() and out.stat().st_size <= target_bytes:
                if on_progress:
                    kb = out.stat().st_size // 1024
                    on_progress(f"gifsicle lossy={lossy_val} → {kb}KB")
                return str(out)

            if out.exists():
                out.unlink()

        except Exception:
            if out.exists():
                out.unlink()
            continue

    return None


# ─── Pillow 기반 GIF 최적화 (폴백) ───
def _optimize_gif_pillow(
    input_path: str,
    target_size_kb: int,
    min_colors: int = 64,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """색상 수를 줄여가며 목표 용량 달성"""
    target_bytes = target_size_kb * 1024

    try:
        img = Image.open(input_path)
        if not getattr(img, 'is_animated', False):
            img.close()
            return input_path

        frames = []
        durations = []
        try:
            while True:
                frames.append(img.copy())
                durations.append(img.info.get('duration', 100))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        img.close()

        loop = frames[0].info.get('loop', 0) if frames else 0
        colors = 256

        while colors >= min_colors:
            out = Path(tempfile.mktemp(suffix='.gif'))
            quantized = []

            for f in frames:
                rgb = f.convert("RGB")
                q = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=1)
                quantized.append(q)
                rgb.close()

            quantized[0].save(
                str(out),
                save_all=True,
                append_images=quantized[1:],
                duration=durations,
                loop=loop,
                optimize=True,
            )
            for q in quantized:
                q.close()

            if out.stat().st_size <= target_bytes:
                if on_progress:
                    kb = out.stat().st_size // 1024
                    on_progress(f"Pillow {colors}색 → {kb}KB")
                for f in frames:
                    f.close()
                return str(out)

            out.unlink(missing_ok=True)
            colors = colors // 2

        for f in frames:
            f.close()
        return None

    except Exception:
        return None


# ─── WebP 품질 하락 최적화 ───
def optimize_webp(
    input_path: str,
    target_size_kb: int = 5000,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """WebP 품질을 내려가며 목표 용량 달성"""
    target_bytes = target_size_kb * 1024
    p = Path(input_path)

    if p.stat().st_size <= target_bytes:
        return input_path

    try:
        img = Image.open(input_path)
        if not getattr(img, 'is_animated', False):
            img.close()
            return input_path

        frames = []
        durations = []
        try:
            while True:
                frames.append(img.copy().convert("RGBA"))
                durations.append(img.info.get('duration', 100))
                img.seek(img.tell() + 1)
        except EOFError:
            pass

        loop = img.info.get('loop', 0)
        img.close()

        for quality in (70, 55, 40, 25, 15):
            out = Path(tempfile.mktemp(suffix='.webp'))

            frames[0].save(
                str(out),
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=loop,
                quality=quality,
                lossless=False,
            )

            if out.stat().st_size <= target_bytes:
                if on_progress:
                    kb = out.stat().st_size // 1024
                    on_progress(f"WebP quality={quality} → {kb}KB")
                for f in frames:
                    f.close()
                return str(out)

            out.unlink(missing_ok=True)

        for f in frames:
            f.close()
        return None

    except Exception:
        return None


# ─── 통합 최적화 (메인 진입점) ───
def optimize_gif(
    input_path: str,
    target_size_kb: int = 5000,
    min_colors: int = 64,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    GIF 최적화: gifsicle lossy → Pillow 색상 감소 순서로 시도.
    """
    p = Path(input_path)
    if p.stat().st_size <= target_size_kb * 1024:
        return input_path

    # 1차: gifsicle (있으면)
    if gifsicle_available():
        if on_progress:
            on_progress("gifsicle lossy 압축 시도 중...")
        result = _optimize_gif_gifsicle(input_path, target_size_kb, on_progress)
        if result:
            return result

    # 2차: Pillow 색상 감소 (메모리 안전 체크)
    # 10MB 이상 GIF는 Pillow 로드 시 메모리 폭발 위험 → 스킵
    file_mb = p.stat().st_size // (1024 * 1024)
    try:
        import psutil
        available_mb = psutil.virtual_memory().available // (1024 * 1024)
    except ImportError:
        available_mb = 4096

    # Pillow는 GIF 전체 프레임을 RGB로 디코딩 → 파일 크기의 ~10배 메모리 사용
    estimated_pillow_mb = file_mb * 10
    if estimated_pillow_mb > available_mb // 2:
        if on_progress:
            on_progress(f"⚠ 파일이 큼 ({file_mb}MB) → Pillow 최적화 스킵 (메모리 부족)")
        return input_path  # 원본 그대로 반환

    if on_progress:
        on_progress("색상 수 줄이기 시도 중...")
    return _optimize_gif_pillow(input_path, target_size_kb, min_colors, on_progress)


def auto_optimize(
    input_path: str,
    target_size_kb: int = 5000,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """포맷 자동 감지 후 최적화"""
    ext = Path(input_path).suffix.lower()
    if ext == '.gif':
        return optimize_gif(input_path, target_size_kb, on_progress=on_progress)
    elif ext == '.webp':
        return optimize_webp(input_path, target_size_kb, on_progress=on_progress)
    return input_path
