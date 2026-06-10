"""
shorts_subtitle.py — ASS 자막 생성 (libass)
장면 노출 구간 목록을 쇼츠 스타일 ASS 자막 파일로 만든다.
(부록 A 분리: 분리 전 shorts_maker.py의 자막부 — 동작 동일)
"""

import sys
from pathlib import Path

from shorts_common import W, H


def _ass_font() -> str:
    return "Malgun Gothic" if sys.platform == "win32" else "NanumGothic"


def _ass_time(s: float) -> str:
    s = max(0.0, float(s))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def _build_ass_file(events: list, path: str, font: str, caption_size: int):
    """events: [(start_sec, end_sec, text), ...] → 쇼츠 스타일 ASS 자막 파일"""
    fs = max(60, min(170, int(caption_size * 1.7)))
    outline = max(4, fs // 12)
    shadow = max(2, fs // 26)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {W}\nPlayResY: {H}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Pop,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,"
        f"100,100,0,0,1,{outline},{shadow},2,80,80,300,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    rows = [header]
    for st, en, text in events:
        t = (text or "").replace("\\", "").replace("{", "").replace("}", "").replace("\n", "\\N").strip()
        if not t:
            continue
        anim = "{\\fad(120,120)\\fscx82\\fscy82\\t(0,160,\\fscx100\\fscy100)}"
        rows.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Pop,,0,0,0,,{anim}{t}")
    Path(path).write_text("\n".join(rows), encoding="utf-8")
