"""
shorts_maker.py — 쇼츠 제작 엔진
사진 여러 장 + 화면 자막 + 나래이션(TTS) + 배경음악 → 세로 9:16 MP4

구조(템플릿) 3종:
  - blur : 흐림 배경 + 사진 가운데 맞춤 (자막 하단)
  - fill : 사진을 9:16로 꽉 채움(크롭) (자막 하단)
  - card : 카드뉴스 스타일 — 흰 배경, 상단 큰 제목(자막) + 사진 아래

나래이션은 타이핑한 글을 음성으로 읽어줍니다(오프라인):
  - 윈도우: 내장 음성(SAPI, 한국어 보이스 있으면 자동 선택)
  - 그 외: espeak-ng
배경음악은 사용자가 고른 음악 파일을 깔아줍니다(저작권 안전).
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Callable

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from utils import find_ffmpeg, generate_output_name, format_filesize

W, H = 1080, 1920  # 9:16 세로
TEMPLATES = ("blur", "fill", "card")


# ════════════════════════════════════════
# 데이터 구조
# ════════════════════════════════════════
class ShortsSegment:
    """쇼츠 한 장면(사진 1장)"""
    def __init__(self, image_path: str = "", duration: float = 3.0,
                 caption: str = "", narration: str = "", template: str = "blur"):
        self.image_path = image_path
        self.duration = duration       # 최소 노출 시간(초). 나래이션이 길면 자동 연장
        self.caption = caption         # 화면에 보이는 자막
        self.narration = narration     # 음성으로 읽을 글
        self.template = template if template in TEMPLATES else "blur"


class ShortsProject:
    """쇼츠 전체 설정"""
    def __init__(self):
        self.segments: List[ShortsSegment] = []
        self.bgm_path: str = ""        # 배경음악 파일(선택)
        self.bgm_volume: float = 0.25  # 0.0~1.0
        self.fps: int = 30
        self.caption_size: int = 56    # 자막 기본 크기(1080 기준)
        self.caption_color: str = "#FFFFFF"
        self.output_path: str = ""
        self.cancelled: bool = False


# ════════════════════════════════════════
# 공통 실행 헬퍼
# ════════════════════════════════════════
def _run(cmd, timeout=300):
    kw = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": timeout}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kw["startupinfo"] = si
    return subprocess.run(cmd, **kw)


def _audio_duration(path: str) -> float:
    try:
        r = _run([_ffprobe_path(), "-v", "quiet", "-show_entries", "format=duration",
                  "-of", "csv=p=0", path], timeout=30)
        return float(r.stdout.decode().strip())
    except Exception:
        return 0.0


def _ffprobe_path() -> str:
    ff = find_ffmpeg()
    if ff:
        cand = str(Path(ff).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe"))
        if Path(cand).exists():
            return cand
    import shutil
    return shutil.which("ffprobe") or "ffprobe"


# ════════════════════════════════════════
# 폰트
# ════════════════════════════════════════
def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    if bold:
        paths = ["C:/Windows/Fonts/malgunbd.ttf", "malgunbd.ttf",
                 "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"]
    else:
        paths = ["C:/Windows/Fonts/malgun.ttf", "malgun.ttf",
                 "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ════════════════════════════════════════
# 이미지 배치 헬퍼
# ════════════════════════════════════════
def _crop_fill(img: Image.Image, tw: int, th: int) -> Image.Image:
    """비율 유지하며 tw×th를 꽉 채우도록 크롭"""
    ratio = max(tw / img.width, th / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    r = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - tw) // 2, (nh - th) // 2
    return r.crop((x, y, x + tw, y + th))


def _fit(img: Image.Image, tw: int, th: int) -> Image.Image:
    """비율 유지하며 tw×th 안에 들어가도록 축소"""
    ratio = min(tw / img.width, th / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    return img.resize((nw, nh), Image.LANCZOS)


def _draw_caption(canvas: Image.Image, text: str, position: str,
                  size: int, color: str):
    """자막을 외곽선+반투명 박스와 함께 그림"""
    if not text.strip():
        return
    base = canvas.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_font(size, bold=True)

    # 줄바꿈: 화면 폭에 맞게 자동 래핑
    max_w = W - 160
    words = text.replace("\n", " \n ").split(" ")
    lines, cur = [], ""
    for w in words:
        if w == "\n":
            lines.append(cur); cur = ""; continue
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    wrapped = "\n".join(lines) if lines else text

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=10, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = max(12, int(size * 0.35))

    x = (W - tw) // 2
    if position == "top":
        y = int(H * 0.10)
    else:  # bottom
        y = H - th - int(H * 0.14)
    text_y = y - bbox[1]

    # 반투명 박스
    draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 150))
    # 외곽선
    bw = max(2, size // 16)
    for dx in range(-bw, bw + 1):
        for dy in range(-bw, bw + 1):
            if dx or dy:
                draw.multiline_text((x + dx, text_y + dy), wrapped, font=font,
                                    fill=(0, 0, 0, 255), spacing=10, align="center")
    draw.multiline_text((x, text_y), wrapped, font=font, fill=color,
                        spacing=10, align="center")

    base.alpha_composite(overlay)
    canvas.paste(base.convert("RGB"), (0, 0))


def render_segment_frame(seg: ShortsSegment, caption_size: int = 56,
                         caption_color: str = "#FFFFFF") -> Image.Image:
    """세그먼트 1장을 1080×1920 프레임으로 렌더링 (미리보기에도 사용)"""
    photo = None
    if seg.image_path and Path(seg.image_path).exists():
        try:
            photo = ImageOps.exif_transpose(Image.open(seg.image_path).convert("RGB"))
        except Exception:
            photo = None

    tpl = seg.template
    cap_pos = "bottom"

    if tpl == "card":
        canvas = Image.new("RGB", (W, H), (245, 245, 247))
        if photo:
            area_top, area_bottom = int(H * 0.30), int(H * 0.92)
            fitted = _fit(photo, W - 100, area_bottom - area_top)
            px = (W - fitted.width) // 2
            py = area_top + (area_bottom - area_top - fitted.height) // 2
            canvas.paste(fitted, (px, py))
        cap_pos = "top"
        cap_color = "#111111" if caption_color.upper() == "#FFFFFF" else caption_color
    elif tpl == "fill":
        canvas = _crop_fill(photo, W, H) if photo else Image.new("RGB", (W, H), (20, 20, 20))
        cap_color = caption_color
    else:  # blur (기본)
        if photo:
            bg = _crop_fill(photo, W, H).filter(ImageFilter.GaussianBlur(45))
            fg = _fit(photo, W, H)
            canvas = bg
            canvas.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
        else:
            canvas = Image.new("RGB", (W, H), (20, 20, 20))
        cap_color = caption_color

    _draw_caption(canvas, seg.caption, cap_pos, caption_size, cap_color)
    try:
        from watermark import apply_to_frame
        canvas = apply_to_frame(canvas)
    except Exception:
        pass
    return canvas


# ════════════════════════════════════════
# 나래이션 (TTS)
# ════════════════════════════════════════
def generate_narration(text: str, out_wav: str) -> Optional[str]:
    """글 → 음성 wav. 윈도우=SAPI, 그 외=espeak-ng. 실패 시 None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        if sys.platform == "win32":
            return _tts_windows(text, out_wav)
        return _tts_espeak(text, out_wav)
    except Exception:
        # 최후 폴백: pyttsx3
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.save_to_file(text, out_wav)
            eng.runAndWait()
            return out_wav if Path(out_wav).exists() else None
        except Exception:
            return None


def _tts_windows(text: str, out_wav: str) -> Optional[str]:
    """윈도우 내장 음성(SAPI). 한국어 보이스 있으면 자동 선택."""
    txt = tempfile.mktemp(suffix=".txt")
    Path(txt).write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        f"$t = Get-Content -Raw -Encoding UTF8 '{txt}';"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$ko = $s.GetInstalledVoices() | "
        "Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1;"
        "if ($ko) { $s.SelectVoice($ko.VoiceInfo.Name) };"
        f"$s.SetOutputToWaveFile('{out_wav}');"
        "$s.Speak($t); $s.Dispose()"
    )
    _run(["powershell", "-NoProfile", "-Command", ps], timeout=120)
    try:
        os.unlink(txt)
    except Exception:
        pass
    return out_wav if Path(out_wav).exists() and Path(out_wav).stat().st_size > 0 else None


def _tts_espeak(text: str, out_wav: str) -> Optional[str]:
    import shutil
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return None
    _run([exe, "-v", "ko", "-s", "150", "-w", out_wav, text], timeout=120)
    return out_wav if Path(out_wav).exists() and Path(out_wav).stat().st_size > 0 else None


# ════════════════════════════════════════
# 빌드
# ════════════════════════════════════════
def build_shorts(project: ShortsProject,
                 on_progress: Optional[Callable[[int, str], None]] = None) -> Optional[str]:
    """쇼츠 프로젝트 → 세로 9:16 MP4 (나래이션 + 배경음악 합성)"""
    ff = find_ffmpeg()
    if not ff:
        if on_progress:
            on_progress(0, "❌ FFmpeg를 찾을 수 없습니다")
        return None
    if not project.segments:
        if on_progress:
            on_progress(0, "❌ 장면이 없습니다")
        return None

    def prog(p, m):
        if on_progress:
            on_progress(p, m)

    work = tempfile.mkdtemp(prefix="shorts_")
    try:
        seg_clips: List[str] = []
        seg_audios: List[str] = []
        total = len(project.segments)

        for i, seg in enumerate(project.segments):
            if project.cancelled:
                return None
            base_pct = int((i / total) * 60)
            prog(base_pct + 3, f"장면 {i + 1}/{total} 만드는 중...")

            # 1) 나래이션 먼저 생성(있으면) → 길이에 맞춰 노출시간 결정
            narr_wav = None
            narr_dur = 0.0
            if seg.narration.strip():
                nw = os.path.join(work, f"narr{i}.wav")
                narr_wav = generate_narration(seg.narration, nw)
                if narr_wav:
                    narr_dur = _audio_duration(narr_wav)

            eff_dur = max(float(seg.duration), narr_dur + 0.4, 1.0)

            # 2) 프레임 렌더 → PNG
            frame = render_segment_frame(seg, project.caption_size, project.caption_color)
            png = os.path.join(work, f"f{i}.png")
            frame.save(png)
            frame.close()

            # 3) 무음 비디오 클립
            clip = os.path.join(work, f"c{i}.mp4")
            r = _run([ff, "-y", "-loop", "1", "-i", png, "-t", f"{eff_dur:.3f}",
                      "-r", str(project.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                      "-vf", f"scale={W}:{H}", "-preset", "veryfast", clip], timeout=300)
            if not Path(clip).exists():
                err = r.stderr.decode("utf-8", "replace")[-200:]
                prog(0, f"❌ 장면 {i+1} 클립 실패: {err.strip()}")
                return None
            seg_clips.append(clip)

            # 4) 세그먼트 오디오: 나래이션을 eff_dur 길이로 (없으면 무음)
            seg_audio = os.path.join(work, f"a{i}.wav")
            if narr_wav:
                _run([ff, "-y", "-i", narr_wav, "-af",
                      f"apad,atrim=0:{eff_dur:.3f},aformat=sample_rates=44100:channel_layouts=stereo",
                      seg_audio], timeout=120)
            if not Path(seg_audio).exists():
                _run([ff, "-y", "-f", "lavfi", "-i",
                      "anullsrc=r=44100:cl=stereo", "-t", f"{eff_dur:.3f}", seg_audio], timeout=60)
            seg_audios.append(seg_audio)

        # 5) 비디오 이어붙이기
        prog(65, "장면 이어붙이는 중...")
        vlist = os.path.join(work, "vlist.txt")
        Path(vlist).write_text("".join(f"file '{c}'\n" for c in seg_clips), encoding="utf-8")
        video_only = os.path.join(work, "video.mp4")
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", vlist,
              "-c", "copy", video_only], timeout=300)
        if not Path(video_only).exists():
            # copy 실패 시 재인코딩 폴백
            _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", vlist,
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                  video_only], timeout=600)
        if not Path(video_only).exists():
            prog(0, "❌ 영상 이어붙이기 실패")
            return None

        # 6) 나래이션 트랙 이어붙이기
        prog(75, "나래이션 합치는 중...")
        alist = os.path.join(work, "alist.txt")
        Path(alist).write_text("".join(f"file '{a}'\n" for a in seg_audios), encoding="utf-8")
        narration_track = os.path.join(work, "narration.wav")
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", alist,
              "-c", "copy", narration_track], timeout=300)
        if not Path(narration_track).exists():
            _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", alist, narration_track], timeout=300)

        total_dur = _audio_duration(narration_track)

        # 7) 배경음악 믹스(있으면)
        prog(85, "배경음악 합치는 중..." if project.bgm_path else "오디오 마무리...")
        final_audio = os.path.join(work, "final.m4a")
        bgm = project.bgm_path
        if bgm and Path(bgm).exists():
            vol = max(0.0, min(1.0, project.bgm_volume))
            _run([ff, "-y", "-i", narration_track, "-stream_loop", "-1", "-i", bgm,
                  "-filter_complex",
                  f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.3f}[bg];"
                  f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]",
                  "-map", "[a]", "-t", f"{total_dur:.3f}",
                  "-c:a", "aac", "-b:a", "160k", final_audio], timeout=300)
        if not Path(final_audio).exists():
            _run([ff, "-y", "-i", narration_track, "-c:a", "aac", "-b:a", "160k",
                  final_audio], timeout=120)

        # 8) 영상 + 오디오 합치기
        prog(93, "최종 합치는 중...")
        if not project.output_path:
            project.output_path = generate_output_name("shorts", "mp4")
        r = _run([ff, "-y", "-i", video_only, "-i", final_audio,
                  "-c:v", "copy", "-c:a", "aac", "-shortest",
                  "-movflags", "+faststart", project.output_path], timeout=300)
        if not Path(project.output_path).exists():
            prog(0, "❌ 최종 합치기 실패")
            return None

        size = format_filesize(Path(project.output_path).stat().st_size)
        prog(100, f"✅ 쇼츠 완성! {size}")
        return project.output_path

    finally:
        try:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass
