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
Style: Default,{font},{size},{primary},&H000000FF,{def_outline_color},&H80000000,0,0,0,0,100,100,0,0,{def_border},{def_outline},{shadow},{alignment},{sub_ml},{sub_ml},{margin_v},1
Style: Title,{font},{title_size},&H00FFFFFF,&H000000FF,{title_outline_color},&HA0000000,0,0,0,0,100,100,0,0,{title_border},{title_outline},{title_shadow},8,{title_ml},{title_ml},{title_margin_v},1

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


# 문장 내 다색 강조 — [노랑]텍스트[/] 처럼 색 이름으로 부분 색칠
COLOR_NAMES = {
    "노랑": "#FFD400", "노란": "#FFD400", "골드": "#FFD400", "옐로": "#FFD400",
    "빨강": "#FF3B30", "빨간": "#FF3B30", "레드": "#FF3B30", "빨": "#FF3B30",
    "초록": "#34C759", "녹색": "#34C759", "그린": "#34C759",
    "파랑": "#0A84FF", "파란": "#0A84FF", "블루": "#0A84FF",
    "하늘": "#5AC8FA", "민트": "#31E1C4",
    "주황": "#FF9500", "오렌지": "#FF9500",
    "분홍": "#FF375F", "핑크": "#FF375F",
    "보라": "#BF5AF2", "퍼플": "#BF5AF2",
    "하양": "#FFFFFF", "흰": "#FFFFFF", "화이트": "#FFFFFF", "흰색": "#FFFFFF",
    "검정": "#111111", "검은": "#111111",
}
_MARKUP_RE = re.compile(r"\[([가-힣A-Za-z]+)\](.*?)(?:\[/[가-힣A-Za-z]*\]|(?=\[[가-힣A-Za-z]+\])|$)", re.S)


def _color_by_name(name: str):
    """색 이름 → hex. ``노란색``처럼 '색' 접미가 붙어도 인식."""
    return COLOR_NAMES.get(name) or COLOR_NAMES.get(name.rstrip("색"))


def colorize_markup(text: str, default_hex: str):
    """``[노랑]...[/]`` 마크업을 ASS 인라인 색으로. 마크업 없으면 None 반환.

    한 줄에 여러 색 가능 (예: ``[노랑]사진만[/] 홍보글이 [초록]뚝딱![/]``).
    닫는 태그 ``[/]``/``[/노랑]``, 안 닫으면 다음 색 태그나 줄 끝까지 적용.
    ``[노란색]``처럼 '색' 접미가 붙어도 인식. 모르는 이름은 그냥 기본색.
    """
    if not re.search(r"\[[가-힣A-Za-z]+\]", text):
        return None
    if not any(_color_by_name(m.group(1)) for m in re.finditer(r"\[([가-힣A-Za-z]+)\]", text)):
        return None  # 아는 색 이름이 하나도 없으면 마크업으로 취급 안 함
    out, last = [], 0
    for m in _MARKUP_RE.finditer(text):
        if m.start() < last:
            continue
        out.append(escape_ass_text(text[last:m.start()]))
        name, seg = m.group(1), m.group(2)
        hexc = _color_by_name(name)
        if hexc:
            out.append(
                "{\\1c" + _inline_color(hexc) + "}"
                + escape_ass_text(seg)
                + "{\\1c" + _inline_color(default_hex) + "}"
            )
        else:
            out.append(escape_ass_text(seg))
        last = m.end()
    out.append(escape_ass_text(text[last:]))
    return "".join(out)


def hook_dialogue_text(hook: str, style) -> str:
    """상단 제목(훅) 본문 — ``제목 | 강조단어``면 그 단어를 강조색으로 팝 (썸네일 임팩트).

    Title 스타일 기본색은 흰색이므로 강조 뒤 흰색으로 복원한다.
    """
    marked = colorize_markup(hook, "#FFFFFF")  # 다색 마크업 우선 (제목 기본 흰색)
    if marked is not None:
        return marked
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


def wrap_text(text: str, max_chars: int) -> str:
    """한 줄이 너무 길면 2줄로 자동 줄바꿈 (중간 근처 공백에서, 없으면 중간 글자).

    이미 줄바꿈이 있거나 짧으면 그대로. 3줄 넘침·잘림 방지 (자막 가독성).
    """
    t = text.strip()
    if max_chars <= 0 or len(t) <= max_chars or "\n" in t:
        return t
    mid, best = len(t) // 2, -1
    for i, ch in enumerate(t):
        if ch == " " and (best == -1 or abs(i - mid) < abs(best - mid)):
            best = i
    if 0 < best < len(t) - 1:
        return t[:best].strip() + "\n" + t[best + 1:].strip()
    return t[:mid] + "\n" + t[mid:]


def dialogue_text(sub, style) -> str:
    """자막 본문 조립 — 페이드 태그 + 강조 단어 인라인 컬러 (지시서 PATCH 5).

    강조색 적용 후 기본색을 명시적으로 복원한다.
    """
    marked = colorize_markup(sub.text, style.primary_color)  # 다색 마크업 우선
    if marked is not None:
        body = marked
    elif sub.highlight and sub.highlight in sub.text:
        pre, _, post = sub.text.partition(sub.highlight)
        body = (
            escape_ass_text(pre)
            + "{\\1c" + _inline_color(style.highlight_color) + "}"
            + escape_ass_text(sub.highlight)
            + "{\\1c" + _inline_color(style.primary_color) + "}"
            + escape_ass_text(post)
        )
    else:  # 순수 텍스트만 자동 줄바꿈 (강조·마크업 있는 건 사용자 편집 존중)
        body = escape_ass_text(wrap_text(sub.text, getattr(style, "wrap_chars", 0)))
    if style.fade:
        body = "{\\fad(100,60)}" + body
    return body


_OVERRIDE_RE = re.compile(r"\{\\[^}]*\}")  # ASS 오버라이드 블록 ({\...})


def band_event_lines(style_name: str, start: str, end: str, body: str,
                     band_on: bool, fade: bool) -> list:
    """배경 띠 이벤트 조립 — 색 강조가 섞인 줄의 '띠 이음새' 제거 (v0.40.1).

    BorderStyle=3 박스는 색 구간(run)마다 따로 그려져, 인라인 색({\\1c})이 있으면
    반투명 박스가 경계에서 겹쳐 세로 줄무늬가 생긴다. 해결: 띠는 색 태그를 뺀
    "유령 이벤트"(글자 투명, 단일 run → 박스 한 장)로 깔고, 글자는 {\\bord0}으로
    박스 없이 위 레이어에 얹는다. 색 없는 줄은 원래도 한 장이라 그대로 둔다.
    """
    prefix = f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,"
    if not (band_on and "\\1c" in body):
        return [prefix + body]
    ghost = _OVERRIDE_RE.sub("", body)          # 색·페이드 태그 제거 → 단일 run
    fad = "\\fad(100,60)" if fade else ""
    return [
        prefix + "{" + fad + "\\1a&HFF&}" + ghost,                       # 띠만 (글자 투명)
        f"Dialogue: 1,{start},{end},{style_name},,0,0,0,," + "{\\bord0}" + body,  # 글자만
    ]


def write_ass(spec: TimelineSpec, out_path) -> str:
    """spec.subtitles(+spec.hook) → .ass 파일 생성. 생성된 경로를 반환.

    자막 크기·여백 설정은 1080×1920 기준 픽셀값 → 캔버스 높이에 비례 스케일.
    (4K 업스케일에서 자막이 절반 크기·절반 높이로 나오던 버그 수정)
    """
    style = spec.style
    sf = spec.canvas.h / 1920.0  # 해상도 스케일 팩터 (1920 기준)

    def sc(v: float) -> int:
        return max(1, round(v * sf))

    # 배경 띠(BorderStyle=3=불투명 박스) — 유튜브 썸네일 스타일. OutlineColour가 박스 색.
    sub_band = getattr(style, "band", False)
    hook_band = getattr(style, "hook_band", True)
    header = _HEADER.format(
        w=spec.canvas.w,
        h=spec.canvas.h,
        font=presets.font_family(style.font),
        size=sc(style.size),
        primary=ass_color(style.primary_color),
        def_border=3 if sub_band else 1,
        # 띠일 때: 반투명 검정 박스 + 박스 여백(Outline), 아니면 글자 외곽선
        def_outline_color="&H90101010" if sub_band else ass_color(style.outline_color),
        def_outline=sc(18) if sub_band else sc(style.outline),
        shadow=0 if sub_band else sc(style.shadow) if style.shadow else 0,
        alignment=presets.subtitle_alignment(style.position),
        margin_v=(
            sc(style.margin_v)
            if style.margin_v is not None
            else presets.subtitle_margin_v(style.position, spec.canvas.h)
        ),
        title_size=round(presets.title_size(spec.canvas.h)
                         * max(0.6, min(1.6, float(getattr(style, "hook_scale", 1.0) or 1.0)))),
        title_border=3 if hook_band else 1,
        title_outline_color="&H90101010" if hook_band else "&H00101010",
        title_outline=sc(20) if hook_band else sc(presets.TITLE_OUTLINE),
        title_shadow=0 if hook_band else presets.TITLE_SHADOW,
        title_margin_v=presets.title_margin_v(spec.canvas.h),
        sub_ml=sc(110),    # 자막 좌우 여백 — 우측 버튼 기둥(~140px)에 긴 줄이 깔리지 않게
        title_ml=sc(90),   # 제목 좌우 여백
    )
    lines = []
    # 상단 제목(훅) — 영상 내내 고정 표시
    if spec.hook.strip():
        lines += band_event_lines(
            "Title", us_to_ass(0), us_to_ass(spec.duration_us),
            hook_dialogue_text(spec.hook.strip(), style),
            band_on=hook_band, fade=False,
        )
    for s in spec.subtitles:
        lines += band_event_lines(
            "Default", us_to_ass(s.start_us), us_to_ass(s.end_us),
            dialogue_text(s, style),
            band_on=sub_band, fade=bool(style.fade),
        )
    Path(out_path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)
