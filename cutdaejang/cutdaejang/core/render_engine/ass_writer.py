"""Timeline Spec → .ass 자막 파일 (기획안 §5.5-2).

스타일 값은 공통 프리셋(presets.py)에서 변환한다 — A안(캡컷) 자막과 시각적 일치가 목표.
Dialogue 시간은 μs → ``h:mm:ss.cc`` 변환, 문장별 1줄.
"""

from __future__ import annotations

import re
from pathlib import Path

from ... import presets
from ...spec import TimelineSpec
from ...utils.timefmt import us_to_ass

# 제목/썸네일 자동 강조 — 숫자(+한국어 단위)는 썸네일에서 가장 강조되는 요소
_NUM_HL = re.compile(
    r"\d[\d,.]*\s*(?:개월|가지|퍼센트|만원|천원|시간|억|만|천|개|배|명|원|일|주|달|년|분|초|위|등|%)?"
)

_HEADER = """\
[Script Info]
; 컷대장 render_engine 자동 생성
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},&H000000FF,{def_outline_color},&H80000000,0,0,0,0,100,100,0,0,{def_border},{def_outline},{shadow},{alignment},60,60,{margin_v},1
Style: Title,{font},{title_size},&H00FFFFFF,&H000000FF,{title_outline_color},&HA0000000,0,0,0,0,100,100,0,0,{title_border},{title_outline},{title_shadow},8,50,50,{title_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """``#RRGGBB`` → ASS ``&HAABBGGRR`` (ASS는 BGR 순서, alpha 0=불투명)."""
    rgb = hex_rgb.lstrip("#")
    if len(rgb) != 6:
        raise ValueError(f"색상 형식 오류(#RRGGBB 필요): {hex_rgb}")
    r, g, b = rgb[0:2], rgb[2:4], rgb[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def escape_ass_text(text: str) -> str:
    """ASS 오버라이드 태그로 해석될 문자 무력화 + 줄바꿈을 ASS 개행으로.

    역슬래시는 뒤에 폭없는 공백(U+200B)을 붙여 ``\\N`` 같은 제어열로 해석되지 않게 한다
    (ASS에는 역슬래시 자체의 이스케이프가 없어 통용되는 우회법).
    """
    return (
        text.replace("\\", "\\​")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _inline_color(hex_rgb: str) -> str:
    """``#RRGGBB`` → 인라인 오버라이드용 ``&HBBGGRR&`` (예: #FFD400 → &H00D4FF&)."""
    rgb = hex_rgb.lstrip("#")
    return f"&H{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&".upper()


def hook_dialogue_text(hook: str, style) -> str:
    """상단 제목(훅) 본문 — ``제목 | 강조단어``면 그 단어를 강조색으로 팝 (썸네일 임팩트).

    Title 스타일 기본색은 흰색이므로 강조 뒤 흰색으로 복원한다.
    """
    text, hl = hook, ""
    if "|" in hook:
        head, _, tail = hook.rpartition("|")
        if head.strip() and tail.strip():
            text, hl = head.strip(), tail.strip()
    if not hl:  # 명시 강조가 없으면 숫자를 자동 강조 (색이 항상 들어가도록)
        m = _NUM_HL.search(text)
        if m and m.group(0).strip():
            hl = m.group(0).strip()
    if hl and hl in text:
        pre, _, post = text.partition(hl)
        return (
            escape_ass_text(pre)
            + "{\\1c" + _inline_color(style.highlight_color) + "}"
            + escape_ass_text(hl)
            + "{\\1c&HFFFFFF&}"
            + escape_ass_text(post)
        )
    return escape_ass_text(text)


def dialogue_text(sub, style) -> str:
    """자막 본문 조립 — 페이드 태그 + 강조 단어 인라인 컬러 (지시서 PATCH 5).

    강조색 적용 후 기본색을 명시적으로 복원한다.
    """
    if sub.highlight and sub.highlight in sub.text:
        pre, _, post = sub.text.partition(sub.highlight)
        body = (
            escape_ass_text(pre)
            + "{\\1c" + _inline_color(style.highlight_color) + "}"
            + escape_ass_text(sub.highlight)
            + "{\\1c" + _inline_color(style.primary_color) + "}"
            + escape_ass_text(post)
        )
    else:
        body = escape_ass_text(sub.text)
    if style.fade:
        body = "{\\fad(100,60)}" + body
    return body


def write_ass(spec: TimelineSpec, out_path) -> str:
    """spec.subtitles(+spec.hook) → .ass 파일 생성. 생성된 경로를 반환."""
    style = spec.style
    # 배경 띠(BorderStyle=3=불투명 박스) — 유튜브 썸네일 스타일. OutlineColour가 박스 색.
    sub_band = getattr(style, "band", False)
    hook_band = getattr(style, "hook_band", True)
    header = _HEADER.format(
        w=spec.canvas.w,
        h=spec.canvas.h,
        font=presets.font_family(style.font),
        size=style.size,
        primary=ass_color(style.primary_color),
        def_border=3 if sub_band else 1,
        # 띠일 때: 반투명 검정 박스 + 박스 여백(Outline), 아니면 글자 외곽선
        def_outline_color="&H90101010" if sub_band else ass_color(style.outline_color),
        def_outline=18 if sub_band else style.outline,
        shadow=0 if sub_band else style.shadow,
        alignment=presets.subtitle_alignment(style.position),
        margin_v=(
            style.margin_v
            if style.margin_v is not None
            else presets.subtitle_margin_v(style.position, spec.canvas.h)
        ),
        title_size=presets.title_size(spec.canvas.h),
        title_border=3 if hook_band else 1,
        title_outline_color="&H90101010" if hook_band else "&H00101010",
        title_outline=20 if hook_band else presets.TITLE_OUTLINE,
        title_shadow=0 if hook_band else presets.TITLE_SHADOW,
        title_margin_v=presets.title_margin_v(spec.canvas.h),
    )
    lines = []
    # 상단 제목(훅) — 영상 내내 고정 표시
    if spec.hook.strip():
        lines.append(
            "Dialogue: 0,{start},{end},Title,,0,0,0,,{text}".format(
                start=us_to_ass(0),
                end=us_to_ass(spec.duration_us),
                text=hook_dialogue_text(spec.hook.strip(), style),
            )
        )
    lines += [
        "Dialogue: 0,{start},{end},Default,,0,0,0,,{text}".format(
            start=us_to_ass(s.start_us), end=us_to_ass(s.end_us), text=dialogue_text(s, style)
        )
        for s in spec.subtitles
    ]
    Path(out_path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)
