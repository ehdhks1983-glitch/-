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
    """글 → 음성. ElevenLabs(설정 시) → 시스템 음성(SAPI/espeak) 폴백. 실패 시 None."""
    text = (text or "").strip()
    if not text:
        return None
    # 1) ElevenLabs (자연스러운 음성, 키 설정 시)
    try:
        from tts_engine import tts_settings, elevenlabs_tts
        if tts_settings.use_elevenlabs:
            mp3 = str(Path(out_wav).with_suffix(".mp3"))
            r = elevenlabs_tts(text, mp3)
            if r:
                return r
    except Exception:
        pass
    # 2) 시스템 음성 폴백 (윈도우 SAPI / espeak)
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
