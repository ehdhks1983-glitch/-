"""
image_merger.py - 이미지 여러 장 → GIF/WebP/APNG 변환 코어
Pillow 기반 프레임 단위 처리 (메모리 안전)
"""

import tempfile
from pathlib import Path
from typing import List, Optional, Callable, Tuple

from PIL import Image

from config import settings
from utils import generate_output_name, format_filesize


class MergeJob:
    """이미지 합치기 작업 데이터"""

    def __init__(self):
        self.image_paths: List[str] = []
        self.frame_delays: List[int] = []  # 개별 프레임 딜레이 (ms)
        self.output_format: str = "gif"
        self.fps: int = 10
        self.default_delay: int = 100      # ms
        self.loop: int = 0                 # 0=무한
        self.resize_mode: str = "largest"  # largest / smallest / custom / none
        self.custom_width: int = 800
        self.custom_height: int = 600
        self.bg_color: str = "#000000"
        self.quality: int = 85             # WebP 품질
        self.output_path: str = ""
        self.cancelled: bool = False

        # 글씨 넣기 (여러 개)
        self.text_overlays: list = []  # [{text, position, size, color, bold}, ...]

    @property
    def delay_ms(self) -> int:
        return self.default_delay

    @delay_ms.setter
    def delay_ms(self, val: int):
        self.default_delay = max(10, val)

    def get_frame_delay(self, index: int) -> int:
        """개별 딜레이가 설정되어 있으면 그걸, 아니면 기본값"""
        if index < len(self.frame_delays) and self.frame_delays[index] > 0:
            return self.frame_delays[index]
        return self.default_delay

    def sync_delays_count(self):
        """이미지 수에 맞게 딜레이 리스트 동기화"""
        while len(self.frame_delays) < len(self.image_paths):
            self.frame_delays.append(0)  # 0 = 기본값 사용


def _parse_hex_color(hex_str: str) -> Tuple[int, int, int]:
    """#RRGGBB → (R, G, B)"""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        return (0, 0, 0)
    return (
        int(hex_str[0:2], 16),
        int(hex_str[2:4], 16),
        int(hex_str[4:6], 16),
    )


def _calculate_target_size(
    images_info: List[Tuple[int, int]],
    mode: str,
    custom_w: int = 800,
    custom_h: int = 600,
) -> Tuple[int, int]:
    """리사이즈 모드에 따른 타겟 크기 계산"""
    if not images_info:
        return (custom_w, custom_h)

    widths = [w for w, h in images_info]
    heights = [h for w, h in images_info]

    if mode == "largest":
        return (max(widths), max(heights))
    elif mode == "smallest":
        return (min(widths), min(heights))
    elif mode == "custom":
        return (custom_w, custom_h)
    elif mode == "fixed_width":
        # 고정 너비 + 비율 유지 (가장 큰 이미지 비율 기준)
        max_w = max(widths)
        max_h = max(heights)
        ratio = max_h / max(1, max_w)
        target_w = custom_w
        target_h = max(1, int(target_w * ratio))
        return (target_w, target_h)
    else:  # none
        return (max(widths), max(heights))


def _resize_and_pad(
    img: Image.Image,
    target_w: int,
    target_h: int,
    bg_color: Tuple[int, int, int],
    transparent: bool = False,
) -> Image.Image:
    """이미지를 타겟 크기에 맞추되 비율 유지 + 배경 패딩"""
    # 비율 유지 리사이즈
    ratio = min(target_w / img.width, target_h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # 캔버스에 센터 배치
    if transparent:
        canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    else:
        canvas = Image.new("RGBA", (target_w, target_h), bg_color + (255,))
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    canvas.paste(resized, (x, y), resized if resized.mode == 'RGBA' else None)

    return canvas


def _draw_text_on_frame(
    frame: Image.Image,
    text: str,
    position: str = "bottom",
    size: int = 28,
    color: str = "#FFFFFF",
    bold: bool = True,
) -> Image.Image:
    """프레임에 텍스트 오버레이 (Pillow)"""
    try:
        from PIL import ImageDraw, ImageFont

        if frame.mode != 'RGBA':
            frame = frame.convert('RGBA')

        # 480p 기준 정규화
        actual_size = max(12, int(size * frame.height / 480))

        # 폰트 로드
        font = None
        if bold:
            paths = ["C:/Windows/Fonts/malgunbd.ttf", "malgunbd.ttf", "arialbd.ttf", "malgun.ttf"]
        else:
            paths = ["C:/Windows/Fonts/malgun.ttf", "malgun.ttf", "arial.ttf"]

        for fp in paths:
            try:
                font = ImageFont.truetype(fp, actual_size)
                break
            except (OSError, IOError):
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size=actual_size)
            except TypeError:
                font = ImageFont.load_default()

        # 오버레이 생성
        overlay = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 텍스트 크기
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=4)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        padding = max(6, int(actual_size * 0.3))

        # 위치
        x = (frame.width - tw) // 2
        if position == "top":
            y = int(frame.height * 0.05)
        elif position == "middle":
            y = (frame.height - th) // 2
        else:
            y = frame.height - th - int(frame.height * 0.05)

        text_y = y - bbox[1]

        # 배경 박스
        draw.rectangle(
            [x - padding, y - padding, x + tw + padding, y + th + padding],
            fill=(0, 0, 0, 180),
        )

        # 테두리
        border = max(1, actual_size // 15)
        for dx in range(-border, border + 1):
            for dy in range(-border, border + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.multiline_text(
                    (x + dx, text_y + dy), text,
                    fill=(0, 0, 0, 255), font=font, spacing=4, align="center",
                )

        # 색상 파싱
        c = color.lstrip('#')
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

        # 텍스트
        draw.multiline_text(
            (x, text_y), text,
            fill=(r, g, b, 255), font=font, spacing=4, align="center",
        )

        result = Image.alpha_composite(frame, overlay)
        overlay.close()
        return result

    except Exception:
        return frame


def merge_images(
    job: MergeJob,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Optional[str]:
    """
    이미지 리스트를 GIF/WebP/APNG로 변환.

    Args:
        job: MergeJob 설정 객체
        on_progress: 콜백 (percent: 0~100, message: str)

    Returns:
        출력 파일 경로 또는 None (실패/취소 시)
    """
    if not job.image_paths:
        return None

    job.sync_delays_count()
    total = len(job.image_paths)

    def progress(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    progress(0, "이미지 분석 중...")

    # ── 1) 이미지 크기 정보 수집 (프레임 단위, 메모리 절약) ──
    sizes = []
    for p in job.image_paths:
        if job.cancelled:
            return None
        try:
            with Image.open(p) as img:
                sizes.append((img.width, img.height))
        except Exception:
            sizes.append((800, 600))  # 읽기 실패 시 기본값

    target_w, target_h = _calculate_target_size(
        sizes, job.resize_mode, job.custom_width, job.custom_height
    )
    bg_rgb = _parse_hex_color(job.bg_color)
    is_transparent = job.bg_color.lower() in ("transparent", "none", "")

    # GIF는 투명 배경 제한적 — 경고
    if is_transparent and job.output_format == "gif":
        progress(3, "⚠ GIF는 1비트 투명만 지원 (가장자리 깨질 수 있음)")

    progress(5, f"캔버스: {target_w}x{target_h}")

    # ── 2) 프레임 생성 ──
    frames: List[Image.Image] = []
    durations: List[int] = []

    for i, path in enumerate(job.image_paths):
        if job.cancelled:
            # 메모리 정리
            for f in frames:
                f.close()
            return None

        pct = 5 + int((i / total) * 70)
        progress(pct, f"프레임 {i+1}/{total} 처리 중...")

        try:
            img = Image.open(path)
            # ── 📱 EXIF 회전 자동 적용 (카카오톡/폰 사진 대응) ──
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            if img.mode not in ('RGBA', 'RGB'):
                img = img.convert('RGBA')
            elif img.mode == 'RGB':
                img = img.convert('RGBA')

            frame = _resize_and_pad(img, target_w, target_h, bg_rgb, transparent=is_transparent)
            img.close()

            # ── ✏️ 글씨 오버레이 적용 (있을 때만, 기존 동작 무영향) ──
            if job.text_overlays:
                for ov in job.text_overlays:
                    try:
                        frame = _draw_text_on_frame(
                            frame,
                            text=ov.get("text", ""),
                            position=ov.get("position", "bottom"),
                            size=ov.get("size", 28),
                            color=ov.get("color", "#FFFFFF"),
                            bold=ov.get("bold", True),
                        )
                    except Exception:
                        pass  # 개별 오버레이 실패해도 변환은 계속

            frames.append(frame)
            durations.append(job.get_frame_delay(i))

        except Exception as e:
            progress(pct, f"⚠ {Path(path).name} 스킵: {e}")
            continue

    if not frames:
        progress(100, "❌ 변환 가능한 이미지가 없습니다")
        return None

    # ── 3) 출력 경로 결정 ──
    if not job.output_path:
        ext = "apng" if job.output_format == "apng" else job.output_format
        job.output_path = generate_output_name("animation", ext)

    progress(80, "파일 생성 중...")

    # ── 4) 포맷별 저장 ──
    try:
        if job.output_format == "gif":
            _save_gif(frames, durations, job)
        elif job.output_format == "webp":
            _save_webp(frames, durations, job)
        elif job.output_format == "apng":
            _save_apng(frames, durations, job)
        else:
            _save_gif(frames, durations, job)
    except Exception as e:
        progress(100, f"❌ 저장 실패: {e}")
        for f in frames:
            f.close()
        return None

    # 메모리 정리
    for f in frames:
        f.close()

    size = Path(job.output_path).stat().st_size
    progress(100, f"✅ 완료! {format_filesize(size)}")
    return job.output_path


def _save_gif(
    frames: List[Image.Image],
    durations: List[int],
    job: MergeJob,
):
    """GIF 저장 (256색 최적화, 1비트 투명 지원)"""
    is_transparent = job.bg_color.lower() in ("transparent", "none", "")

    converted = []
    for f in frames:
        if is_transparent:
            # RGBA → 투명 배경 GIF: alpha=0 픽셀을 투명색으로 지정
            rgb = f.convert("RGB")
            alpha = f.split()[3]
            quantized = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=1)
            # 투명 인덱스를 마지막 팔레트 엔트리로 설정
            mask = alpha.point(lambda a: 255 if a < 128 else 0)
            quantized.paste(255, mask=mask)
            quantized.info['transparency'] = 255
            converted.append(quantized)
            rgb.close()
        else:
            rgb = f.convert("RGB")
            quantized = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=1)
            converted.append(quantized)
            rgb.close()

    save_kwargs = {
        "save_all": True,
        "append_images": converted[1:],
        "duration": durations,
        "loop": job.loop,
        "optimize": True,
    }
    if is_transparent:
        save_kwargs["transparency"] = 255
        save_kwargs["disposal"] = 2  # 이전 프레임 클리어 (투명 유지)

    converted[0].save(job.output_path, **save_kwargs)

    for c in converted:
        c.close()


def _save_webp(
    frames: List[Image.Image],
    durations: List[int],
    job: MergeJob,
):
    """WebP 애니메이션 저장 (풀컬러, 고효율)"""
    rgba_frames = [f.convert("RGBA") for f in frames]

    rgba_frames[0].save(
        job.output_path,
        save_all=True,
        append_images=rgba_frames[1:],
        duration=durations,
        loop=job.loop,
        quality=job.quality,
        lossless=False,
    )

    for r in rgba_frames:
        r.close()


def _save_apng(
    frames: List[Image.Image],
    durations: List[int],
    job: MergeJob,
):
    """APNG 저장 (풀컬러 PNG 애니메이션)"""
    rgba_frames = [f.convert("RGBA") for f in frames]

    rgba_frames[0].save(
        job.output_path,
        save_all=True,
        append_images=rgba_frames[1:],
        duration=durations,
        loop=job.loop,
    )

    for r in rgba_frames:
        r.close()


def estimate_output_size(
    image_count: int,
    avg_width: int,
    avg_height: int,
    output_format: str,
    quality: int = 85,
) -> int:
    """대략적인 출력 파일 크기 추정 (바이트)"""
    pixels = avg_width * avg_height * image_count

    if output_format == "gif":
        # GIF: 256색, 프레임당 ~0.3~0.8 bytes/pixel (압축 후)
        return int(pixels * 0.5)
    elif output_format == "webp":
        # WebP: 품질에 따라 0.05~0.3 bytes/pixel
        ratio = 0.05 + (quality / 100) * 0.25
        return int(pixels * ratio)
    elif output_format == "apng":
        # APNG: 무손실, ~1.0~2.0 bytes/pixel
        return int(pixels * 1.5)

    return int(pixels * 0.5)
