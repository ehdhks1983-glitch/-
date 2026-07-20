"""🔔 효과음 자동 (v0.53) — 뿅(강조)·휙(전환)·띠링(제목 등장) 합성·배치·믹스.

효과음 파일을 내려받지 않고 ffmpeg로 직접 합성한다(저작권 걱정 0).
- resources/sfx/뿅.wav·휙.wav·띠링.wav 가 없으면 처음 한 번 만들어 캐시.
- 사용자가 같은 이름으로 자기 효과음(wav/mp3)을 넣어두면 그걸 우선 사용.

배치 규칙 (spec 기준):
- 띠링: 상단 제목(훅)이 있으면 영상 시작 0.15초
- 뿅:   강조(하이라이트/색 마크업)가 있는 문장의 시작 (앞에서부터 최대 6개)
- 휙:   장면 그림이 넘어가는 시점 (배경이 ai_scenes 슬라이드일 때, 최대 12개)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ..spec import Sfx, TimelineSpec
from ..utils import ffmpeg as ff

SFX_DIR = Path(__file__).resolve().parents[2] / "resources" / "sfx"

# 이름 → (파일명, ffmpeg 합성 필터)
_SYNTH = {
    "pop": ("뿅.wav",
            # 위로 감기는 짧은 처프 + 빠른 감쇠 = 만화 '뿅'
            "aevalsrc='0.55*sin(2*PI*(650+2600*t)*t)*exp(-14*t)':d=0.18:s=44100"),
    "whoosh": ("휙.wav",
               # 분홍 잡음을 대역 통과 + 가운데 볼록한 볼륨 = 스치는 '휙'
               "anoisesrc=d=0.30:c=pink:r=44100:a=0.7,"
               "highpass=f=400,lowpass=f=2600,"
               "volume='if(lt(t\\,0.12)\\,t/0.12\\,(0.30-t)/0.18)':eval=frame"),
    "ding": ("띠링.wav",
             # 배음 두 개 + 느린 감쇠 = 맑은 '띠링'
             "aevalsrc='0.42*(sin(2*PI*1318*t)+0.55*sin(2*PI*1976*t))*exp(-5.5*t)'"
             ":d=0.8:s=44100"),
}

# wav를 마지막에 — 합성 캐시가 wav라서, 사용자 mp3 등이 있으면 그게 우선되도록
_USER_EXTS = (".mp3", ".m4a", ".ogg", ".flac", ".wav")


def ensure_sfx(sfx_dir: Optional[Path] = None) -> dict:
    """효과음 3종 준비 — 사용자 파일 우선, 없으면 합성해 캐시. {이름: 경로} 반환."""
    out_dir = Path(sfx_dir) if sfx_dir else SFX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (fname, filt) in _SYNTH.items():
        stem = Path(fname).stem
        user = next((p for ext in _USER_EXTS
                     if (p := out_dir / f"{stem}{ext}").is_file() and p.stat().st_size > 200),
                    None)
        if user is not None:
            paths[name] = str(user)
            continue
        dest = out_dir / fname
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", filt, "-ar", "44100", "-ac", "1", str(dest)])
        paths[name] = str(dest)
    return paths


_MARKUP = "["  # [노랑]… 색 마크업이 있는 문장도 '강조 문장'으로 취급


def build_events(spec: TimelineSpec, paths: dict, cfg: dict,
                 scene_starts_us: Optional[List[int]] = None) -> List[Sfx]:
    """spec을 읽어 효과음 이벤트 목록 생성 (배치 규칙은 모듈 docstring)."""
    vol = float(cfg.get("volume_db", -13))
    events: List[Sfx] = []
    if spec.hook.strip() and paths.get("ding"):
        events.append(Sfx(path=paths["ding"], start_us=150_000, gain_db=vol, name="ding"))
    if paths.get("pop"):
        n = 0
        for clip, sub in zip(spec.audio, spec.subtitles):
            emphasized = bool((sub.highlight or "").strip()) or _MARKUP in (sub.text or "")
            if emphasized and clip.start_us > 300_000:  # 첫 문장 머리는 띠링과 겹쳐 생략
                events.append(Sfx(path=paths["pop"], start_us=clip.start_us,
                                  gain_db=vol, name="pop"))
                n += 1
                if n >= 6:
                    break
    if scene_starts_us and paths.get("whoosh"):
        for t in scene_starts_us[1:13]:  # 첫 장면 시작은 제외, 최대 12번
            events.append(Sfx(path=paths["whoosh"], start_us=max(0, t - 120_000),
                              gain_db=vol - 3, name="whoosh"))
    events.sort(key=lambda e: e.start_us)
    return events


def mix_sfx(voice_path: str, events: List[Sfx], out_path: str) -> str:
    """보이스 트랙 위에 효과음들을 시점별로 얹는다 (길이는 보이스 그대로).

    이벤트가 없거나 전부 파일이 없으면 원본을 복사만 한다.
    """
    usable = [e for e in events if e.path and Path(e.path).is_file()]
    if not usable:
        shutil.copyfile(voice_path, out_path)
        return str(out_path)
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(voice_path)]
    for e in usable:
        args += ["-i", e.path]
    parts = []
    for k, e in enumerate(usable, start=1):
        ms = max(0, e.start_us // 1000)
        parts.append(f"[{k}:a]volume={e.gain_db}dB,adelay={ms}:all=1[s{k}]")
    inputs = "[0:a]" + "".join(f"[s{k}]" for k in range(1, len(usable) + 1))
    # duration=first → 보이스 길이 유지. normalize=0 → 보이스 볼륨 그대로.
    parts.append(f"{inputs}amix=inputs={len(usable) + 1}:duration=first:normalize=0[out]")
    args += ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "44100",
             str(out_path)]
    try:
        ff.run(args)
    except (ff.FFmpegError, subprocess.SubprocessError):
        shutil.copyfile(voice_path, out_path)  # 효과음 실패가 렌더를 막으면 안 됨
    return str(out_path)
