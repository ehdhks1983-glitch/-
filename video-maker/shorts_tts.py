"""
shorts_tts.py — 나래이션(TTS)
글 → 음성. ElevenLabs(설정 시) → 시스템 음성(SAPI/espeak) → pyttsx3 폴백.
(부록 A 분리: 분리 전 shorts_maker.py의 나래이션부 — 동작 동일.
 Edge-TTS는 1-2 단계에서 이 모듈에 추가된다.)
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from shorts_common import _run


def generate_narration(text: str, out_wav: str) -> Optional[str]:
    """글 → 음성. 엔진 설정에 따라 폴백. 실패 시 None.
      - auto       : ElevenLabs(키 있을 때) → Edge-TTS → 시스템(SAPI/espeak)
      - elevenlabs : ElevenLabs → Edge-TTS → 시스템
      - edge       : Edge-TTS → 시스템
      - system     : 시스템만
    Edge-TTS는 무료 고품질이라 시스템 로봇 음성보다 항상 나은 폴백으로 둔다(1-2)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        from tts_engine import tts_settings
        engine = (tts_settings.get("engine") or "auto").lower()
    except Exception:
        engine = "auto"
    try_el = engine in ("auto", "elevenlabs")
    try_edge = engine in ("auto", "elevenlabs", "edge")

    # 1) ElevenLabs (자연스러운 음성, 키 설정 시)
    if try_el:
        try:
            from tts_engine import tts_settings as _ts, elevenlabs_tts
            if _ts.use_elevenlabs:
                mp3 = str(Path(out_wav).with_suffix(".mp3"))
                r = elevenlabs_tts(text, mp3)
                if r:
                    return r
        except Exception:
            pass
    # 2) Edge-TTS (무료 고품질, 네트워크 필요)
    if try_edge:
        try:
            from tts_engine import edge_tts_synthesize
            mp3 = str(Path(out_wav).with_suffix(".mp3"))
            r = edge_tts_synthesize(text, mp3)
            if r:
                return r
        except Exception:
            pass
    # 3) 시스템 음성 폴백 (윈도우 SAPI / espeak) → 최후 pyttsx3
    try:
        if sys.platform == "win32":
            return _tts_windows(text, out_wav)
        return _tts_espeak(text, out_wav)
    except Exception:
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
