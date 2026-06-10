"""
photo_motion.py — ✨ 사진 1장 → 움직이는 움짤 (켄번스/줌/패닝)
정지 이미지에서 프레임을 조금씩 잘라내며 '카메라가 움직이는' 느낌을 만들어
GIF/WebP로 저장한다. 무료·오프라인 (ffmpeg 불필요, PIL만 사용).
인코딩/팔레트/워터마크는 기존 image_merger·optimizer·watermark를 재사용한다.
"""

from pathlib import Path
from typing import Callable, List, Optional

from PIL import Image

from utils import generate_output_name, format_filesize


# 효과 키 → 한글 표시명 (UI 드롭다운에 그대로 사용)
EFFECTS = {
    "ken_burns": "켄번스 (확대+이동)",
    "zoom_in": "줌 인 (확대)",
    "zoom_out": "줌 아웃 (축소)",
    "pan_right": "오른쪽으로 이동",
    "pan_left": "왼쪽으로 이동",
    "pan_down": "아래로 이동",
    "pan_up": "위로 이동",
}


class MotionJob:
    def __init__(self):
        self.input_path: str = ""
        self.output_path: str = ""
        self.output_format: str = "gif"      # gif / webp
        self.effect: str = "ken_burns"
        self.duration: float = 4.0           # 초
        self.fps: int = 20
        self.zoom: float = 1.3               # 최대 확대 배율
        self.loop: int = 0                   # 0 = 무한
        self.out_height: int = 480           # 출력 높이(px), 너비는 비율 유지
        self.quality_mode: str = "balanced"  # best / balanced / fast
        self.gif_lossy: int = 30             # gifsicle 마무리 압축
        self.bg_color: str = "#000000"
        self.boomerang: bool = True          # 왕복 반복(이음새 없는 매끈한 루프)
        self.cancelled: bool = False


def _ease(t: float) -> float:
    """smoothstep — 시작/끝을 부드럽게 (가감속)"""
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def generate_motion_frames(
    img: Image.Image,
    effect: str,
    n_frames: int,
    zoom: float,
    out_w: int,
    out_h: int,
    on_progress: Optional[Callable] = None,
    is_cancelled: Optional[Callable] = None,
) -> List[Image.Image]:
    """정지 이미지 → 움직임이 적용된 프레임 리스트"""
    src = img.convert("RGB")
    W, H = src.size
    zoom = max(1.05, min(2.5, float(zoom)))
    frames: List[Image.Image] = []

    for i in range(n_frames):
        if is_cancelled and is_cancelled():
            break
        t = _ease(i / (n_frames - 1)) if n_frames > 1 else 0.0

        # 줌 배율 z 와 크롭 중심(cfx, cfy: 0~1 비율) 결정
        if effect == "zoom_in":
            z = _lerp(1.0, zoom, t); cfx = cfy = 0.5
        elif effect == "zoom_out":
            z = _lerp(zoom, 1.0, t); cfx = cfy = 0.5
        elif effect == "ken_burns":
            z = _lerp(1.0, zoom, t)
            cfx = _lerp(0.38, 0.62, t); cfy = _lerp(0.43, 0.57, t)
        else:
            # 패닝: 줌 고정, 중심을 한 축으로 끝→끝까지 (가능한 최대 범위)
            z = zoom
            m = 1.0 / (2.0 * z)            # 중심이 갈 수 있는 가장자리 여백(비율)
            lo, hi = m, 1.0 - m
            cfx = cfy = 0.5
            if effect == "pan_right":
                cfx = _lerp(lo, hi, t)
            elif effect == "pan_left":
                cfx = _lerp(hi, lo, t)
            elif effect == "pan_down":
                cfy = _lerp(lo, hi, t)
            elif effect == "pan_up":
                cfy = _lerp(hi, lo, t)

        crop_w = W / z
        crop_h = H / z
        cx = cfx * W
        cy = cfy * H
        x = min(max(cx - crop_w / 2.0, 0.0), W - crop_w)
        y = min(max(cy - crop_h / 2.0, 0.0), H - crop_h)
        # 서브픽셀 정밀도로 리샘플 (정수 크롭 시 생기는 '뚝뚝' 끊김 제거)
        box = (x, y, x + crop_w, y + crop_h)
        frame = src.resize((out_w, out_h), Image.LANCZOS, box=box)
        frames.append(frame)

        if on_progress and (i % 4 == 0):
            on_progress(int(10 + 60 * i / max(1, n_frames)), f"프레임 생성 {i + 1}/{n_frames}")

    return frames


def create_motion(job: MotionJob, on_progress: Optional[Callable] = None) -> Optional[str]:
    """MotionJob → 움짤 파일 생성. 성공 시 출력 경로, 실패 시 None."""
    def progress(p, m):
        if on_progress:
            on_progress(p, m)

    try:
        progress(3, "이미지 여는 중...")
        img = Image.open(job.input_path)
        img.load()
    except Exception as e:
        progress(100, f"❌ 이미지 열기 실패: {e}")
        return None

    W, H = img.size
    out_h = max(2, int(job.out_height)); out_h -= out_h % 2
    out_w = max(2, round(W / max(1, H) * out_h)); out_w -= out_w % 2

    n_total = max(2, min(400, int(round(job.duration * job.fps))))
    if getattr(job, "boomerang", False):
        # 왕복(팔린드롬): 앞으로 갔다 되돌아와 이음새/정점이 매끈 → 끊김 없는 반복
        n_fwd = max(2, n_total // 2 + 1)
        fwd = generate_motion_frames(
            img, job.effect, n_fwd, job.zoom, out_w, out_h,
            on_progress=progress, is_cancelled=lambda: job.cancelled,
        )
        frames = fwd + [f.copy() for f in fwd[-2:0:-1]] if len(fwd) > 2 else fwd
    else:
        frames = generate_motion_frames(
            img, job.effect, n_total, job.zoom, out_w, out_h,
            on_progress=progress, is_cancelled=lambda: job.cancelled,
        )
    img.close()
    if job.cancelled or not frames:
        return None

    # ── 워터마크 (전역 설정이 켜져 있을 때) ──
    try:
        from watermark import watermark, apply_to_frame
        if watermark.active:
            progress(74, "워터마크 적용 중...")
            wm = []
            for f in frames:
                nf = apply_to_frame(f)
                wm.append(nf)
                if nf is not f:
                    f.close()
            frames = wm
    except Exception:
        pass

    # ── 출력 경로 ──
    if not job.output_path:
        ext = job.output_format if job.output_format in ("gif", "webp") else "gif"
        base = Path(job.input_path).stem + "_motion"
        job.output_path = generate_output_name(base, ext)

    durations = [int(round(1000.0 / max(1, job.fps)))] * len(frames)

    # ── 저장 (image_merger 인코더 재사용: GIF=글로벌 팔레트, WebP=풀컬러) ──
    progress(82, "파일 생성 중...")
    try:
        from image_merger import _save_gif, _save_webp, MergeJob
        mj = MergeJob()
        mj.loop = job.loop
        mj.bg_color = job.bg_color
        mj.output_path = job.output_path
        mj.quality = {"best": 92, "balanced": 80, "fast": 65}.get(job.quality_mode, 80)
        if job.output_format == "webp":
            _save_webp(frames, durations, mj)
        else:
            _save_gif(frames, durations, mj)
    except Exception as e:
        progress(100, f"❌ 저장 실패: {e}")
        for f in frames:
            try:
                f.close()
            except Exception:
                pass
        return None

    for f in frames:
        try:
            f.close()
        except Exception:
            pass

    # ── GIF 용량 최적화 (화질 프리셋) ──
    if job.output_format == "gif" and job.gif_lossy > 0:
        try:
            from optimizer import polish_gif
            progress(95, "용량 최적화 중...")
            polish_gif(job.output_path, job.gif_lossy)
        except Exception:
            pass

    try:
        size = Path(job.output_path).stat().st_size
        progress(100, f"✅ 완료! {format_filesize(size)}")
    except Exception:
        progress(100, "✅ 완료!")
    return job.output_path
