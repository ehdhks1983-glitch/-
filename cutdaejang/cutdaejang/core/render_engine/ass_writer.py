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
Style: Title,{title_font},{title_size},{title_primary},&H000000FF,{title_outline_color},&HA0000000,0,0,0,0,100,100,0,{title_angle},{title_border},{title_outline},{title_shadow},8,{title_ml},{title_ml},{title_margin_v},1
Style: Info,{font},{info_size},{info_primary},&H000000FF,&H00101010,&HA0000000,0,0,0,0,100,100,0,0,1,{info_outline},2,5,60,60,0,1

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


# 💬 본문 자막 스타일 프리셋 (v0.54) — Default 스타일의 색·테두리·띠를 통째로.
# "band" 키가 있으면 사용자의 subtitle.band 설정을 프리셋이 덮는다.
# 🌈 다색 팝(v0.73): pop_rotate=True면 문장마다 아래 팔레트 색을 번갈아 칠한다.
POP_PALETTE = ["#FF3B30", "#31E1C4", "#FFD400", "#FF7A00", "#5AC8FA", "#FF375F"]
SUB_STYLES = {
    "기본": {},
    "예능 노랑": {"primary": "#FFE14D", "band": False, "outline": 6,
                "outline_color": "#101010", "shadow": 2, "highlight": "#FF3B30"},
    "말풍선 띠": {"primary": "#141414", "band": True, "band_color": "&H00F5F5F5",
                "highlight": "#D62B00"},
    "네온": {"primary": "#9CFFF0", "band": False, "outline": 3,
            "outline_color": "#0FB5A0", "shadow": 0, "blur": 4},
    # 🌈 다색 팝 — 문장마다 색이 바뀌는 굵은 흰 테두리 자막 (인스타 릴스 밈 느낌)
    "다색 팝": {"primary": "#FFFFFF", "band": False, "outline": 6,
              "outline_color": "#FFFFFF", "shadow": 3, "pop_rotate": True},
    # ⬛ 블랙 박스 — 검은 띠 위 흰 글자 + 노랑 강조 (참고 릴스 상단 제목형)
    "블랙 박스": {"primary": "#FFFFFF", "band": True, "band_color": "&H00121212",
               "highlight": "#FFD400"},
}

# 🪧 상단 제목 스타일 프리셋 (v0.52) — 글자색·테두리·띠를 통째로 바꾼다.
# band=None이면 사용자의 hook_band 설정 유지, 아니면 프리셋이 강제.
HOOK_STYLES = {
    "기본": {},
    "예능 노랑": {"primary": "#FFD400", "band": False, "outline": 7,
                "outline_color": "#101010", "shadow": 2, "highlight": "#FF3B30"},
    "화이트 박스": {"primary": "#141414", "band": True, "band_color": "&H00F2F2F2",
                 "highlight": "#D62B00"},
    "네온": {"primary": "#9CFFF0", "band": False, "outline": 3,
            "outline_color": "#0FB5A0", "shadow": 0, "blur": 5},
    # 🌈 다색 팝 — 제목도 굵은 흰 테두리에 팝 컬러 (다색 자막과 세트)
    "다색 팝": {"primary": "#FFFFFF", "band": False, "outline": 7,
              "outline_color": "#FFFFFF", "shadow": 3, "pop_rotate": True},
    # ⬛ 블랙 박스 — 검은 띠 위 흰 제목 + 노랑 강조 (참고 릴스 스샷1)
    "블랙 박스": {"primary": "#FFFFFF", "band": True, "band_color": "&H00121212",
               "highlight": "#FFD400"},
}


def hook_dialogue_text(hook: str, style, primary: str = "#FFFFFF",
                       highlight: str = "", pop_color: str = "") -> str:
    """상단 제목(훅) 본문 — ``제목 | 강조단어``면 그 단어를 강조색으로 팝 (썸네일 임팩트).

    강조 뒤에는 제목 기본색(프리셋별로 다름 — v0.52)으로 복원한다.
    pop_color(v0.73 다색 팝)면 수동 마크업·강조가 없는 제목 전체를 그 색으로 칠한다.
    """
    hl_color = highlight or style.highlight_color
    marked = colorize_markup(hook, primary)  # 다색 마크업 우선
    if marked is not None:
        return marked
    if pop_color and "|" not in hook:  # 🌈 다색 팝 제목 — 전체를 팝 컬러로
        return "{\\1c" + _inline_color(pop_color) + "}" + escape_ass_text(hook)
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
            + "{\\1c" + _inline_color(hl_color) + "}"
            + escape_ass_text(hl)
            + "{\\1c" + _inline_color(primary) + "}"
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


TYPING_CPS = 20  # ⌨ 타이핑 자막(v0.74) 속도 — 초당 글자수 (인스타·틱톡 감성)


def _typing_body(text: str, line_color: str, cps: int = TYPING_CPS) -> str:
    """⌨ 타이핑 등장(v0.74) — 글자를 하나씩 찍어 보여준다 (화면 중앙 인스타·틱톡용).

    글자마다 처음엔 투명(\\alpha&HFF&)이었다가 제 차례(t_i)에 \\t로 나타난다.
    줄바꿈(\\N)은 글자수에 안 세고 그대로 둔다. 색은 줄 전체에 한 번만 건다.
    """
    out = ["{\\1c" + _inline_color(line_color) + "}"] if line_color else []
    i = 0
    for ch in text:
        if ch == "\n":
            out.append("\\N")
            continue
        t = round(i * 1000.0 / max(1, cps))
        out.append("{\\alpha&HFF&\\t(%d,%d,\\alpha&H00&)}" % (t, t + 30))
        out.append(escape_ass_text(ch))
        i += 1
    return "".join(out)


def dialogue_text(sub, style, pop_color: str = "") -> str:
    """자막 본문 조립 — 페이드 태그 + 강조 단어 인라인 컬러 (지시서 PATCH 5).

    강조색 적용 후 기본색을 명시적으로 복원한다.
    pop_color(v0.73 다색 팝)가 있으면 수동 마크업이 없는 문장 전체를 그 색으로 칠한다.
    anim=="type"(v0.74)면 글자를 하나씩 찍는 타이핑으로 등장한다.
    """
    marked = colorize_markup(sub.text, style.primary_color)  # 다색 마크업 우선
    if marked is None and getattr(style, "anim", "none") == "type":
        # ⌨ 타이핑 — 마크업 없을 때만 (수동 색은 위에서 존중). 타이핑이 등장연출이라 fade/pop 미적용.
        line_color = pop_color or style.primary_color
        return _typing_body(wrap_text(sub.text, getattr(style, "wrap_chars", 0)), line_color)
    if marked is not None:
        body = marked
    elif pop_color:  # 🌈 다색 팝 — 문장 전체를 회전색으로 (수동 색·강조는 위에서 우선)
        body = ("{\\1c" + _inline_color(pop_color) + "}"
                + escape_ass_text(wrap_text(sub.text, getattr(style, "wrap_chars", 0))))
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
    if getattr(style, "anim", "none") == "pop":
        # 살짝 작게 시작해 130ms 만에 원래 크기로 — 등장 팝 (v0.43).
        # 띠(band) 모드에서는 유령 레이어가 태그를 걷어내므로 띠는 고정, 글자만 팝.
        body = "{\\fscx86\\fscy86\\t(0,130,\\fscx100\\fscy100)}" + body
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
    # 색 강조(\1c)나 팝 애니메이션(\fscx)이 있으면 2층: 띠는 태그 없는 유령 레이어로
    # 고정해 그리고(이음새·박스 요동 방지), 글자만 위 레이어에서 색·팝을 적용한다.
    if not (band_on and ("\\1c" in body or "\\fscx" in body)):
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

    wide = spec.canvas.w > spec.canvas.h  # 🖥 가로 롱폼 (v0.62)
    if wide and getattr(style, "wrap_chars", 0):
        # 가로 화면은 한 줄이 길어도 안전 — 세로 기준(16자)을 자동 확장 (16→27)
        from dataclasses import replace  # noqa: PLC0415

        style = replace(style, wrap_chars=min(30, round(style.wrap_chars * 1.7)))
    # 💬 본문 자막 프리셋 (v0.54) — 색·강조·띠를 프리셋 값으로 덮은 유효 스타일 사용
    ss = SUB_STYLES.get(getattr(style, "sub_style", "기본") or "기본", {})
    if ss:
        from dataclasses import replace  # noqa: PLC0415

        style = replace(
            style,
            primary_color=ss.get("primary", style.primary_color),
            highlight_color=ss.get("highlight", style.highlight_color),
            outline_color=ss.get("outline_color", style.outline_color),
            outline=ss.get("outline", style.outline),
            shadow=ss.get("shadow", style.shadow),
            band=ss["band"] if "band" in ss else style.band,
        )
    # 배경 띠(BorderStyle=3=불투명 박스) — 유튜브 썸네일 스타일. OutlineColour가 박스 색.
    sub_band = getattr(style, "band", False)
    hs = HOOK_STYLES.get(getattr(style, "hook_style", "기본") or "기본", {})
    hook_band = hs["band"] if "band" in hs else getattr(style, "hook_band", True)
    hook_primary = hs.get("primary", "#FFFFFF")
    header = _HEADER.format(
        w=spec.canvas.w,
        h=spec.canvas.h,
        font=presets.font_family(style.font),
        title_font=presets.font_family(getattr(style, "hook_font", "") or style.font),
        title_angle=4 if getattr(style, "hook_tilt", False) else 0,
        size=sc(style.size),
        primary=ass_color(style.primary_color),
        def_border=3 if sub_band else 1,
        # 띠일 때: 박스 색(기본 반투명 검정, 프리셋이 지정하면 그 색), 아니면 글자 외곽선
        def_outline_color=(ss.get("band_color", "&H90101010") if sub_band
                           else ass_color(style.outline_color)),
        def_outline=sc(18) if sub_band else sc(style.outline),
        shadow=0 if sub_band else sc(style.shadow) if style.shadow else 0,
        alignment=presets.subtitle_alignment(style.position),
        margin_v=(
            sc(style.margin_v)
            if style.margin_v is not None
            else presets.subtitle_margin_v(style.position, spec.canvas.h)
        ),
        title_size=round(presets.title_size(spec.canvas.h)
                         * (1.45 if wide else 1.0)  # 가로에선 높이 비례만으론 작아 보정 (v0.62)
                         * max(0.6, min(1.6, float(getattr(style, "hook_scale", 1.0) or 1.0)))),
        title_primary=ass_color(hook_primary),
        title_border=3 if hook_band else 1,
        title_outline_color=(hs.get("band_color", "&H90101010") if hook_band
                             else ass_color(hs.get("outline_color", "#101010"))),
        title_outline=sc(20) if hook_band else sc(hs.get("outline", presets.TITLE_OUTLINE)),
        title_shadow=0 if hook_band else hs.get("shadow", presets.TITLE_SHADOW),
        title_margin_v=presets.title_margin_v(spec.canvas.h),
        info_size=round(spec.canvas.h * 0.085),          # 🔢 숫자 인포 팝 (v0.56)
        info_primary=ass_color(style.highlight_color),
        info_outline=sc(9),
        sub_ml=sc(110),    # 자막 좌우 여백 — 우측 버튼 기둥(~140px)에 긴 줄이 깔리지 않게
        title_ml=sc(90),   # 제목 좌우 여백
    )
    lines = []
    # 상단 제목(훅) — 영상 내내 고정 표시
    if spec.hook.strip():
        hook_body = hook_dialogue_text(
            spec.hook.strip(), style, primary=hook_primary,
            highlight=hs.get("highlight", ""),
            pop_color=POP_PALETTE[0] if hs.get("pop_rotate") else "")  # 🌈 다색 팝 (v0.73)
        if hs.get("blur"):  # 네온 — 외곽선을 번지게 (글로우)
            hook_body = "{\\blur" + str(max(2, sc(hs["blur"]))) + "}" + hook_body
        lines += band_event_lines(
            "Title", us_to_ass(0), us_to_ass(spec.duration_us),
            hook_body,
            band_on=hook_band, fade=False,
        )
    # 🔢 숫자 인포 팝 (v0.56) — 문장 속 숫자를 중상단에 크게, 팝 등장 + 페이드 아웃
    cx, cy = spec.canvas.w // 2, round(spec.canvas.h * 0.40)
    for ip in getattr(spec, "infopops", []) or []:
        lines.append(
            f"Dialogue: 1,{us_to_ass(ip.start_us)},{us_to_ass(ip.end_us)},Info,,0,0,0,,"
            + "{\\an5\\pos(" + str(cx) + "," + str(cy) + ")"
            + "\\fscx55\\fscy55\\t(0,140,\\fscx100\\fscy100)\\fad(60,200)}"
            + escape_ass_text(ip.text))

    pop_on = bool(ss.get("pop_rotate"))  # 🌈 다색 팝 — 문장마다 색 번갈아 (v0.73)
    for i, s in enumerate(spec.subtitles):
        pop = POP_PALETTE[i % len(POP_PALETTE)] if pop_on else ""
        body = dialogue_text(s, style, pop_color=pop)
        if ss.get("blur"):  # 네온 자막 — 외곽선 글로우 (띠 없음 프리셋에서만)
            body = "{\\blur" + str(max(2, sc(ss["blur"]))) + "}" + body
        lines += band_event_lines(
            "Default", us_to_ass(s.start_us), us_to_ass(s.end_us),
            body,
            band_on=sub_band, fade=bool(style.fade),
        )
    Path(out_path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)
