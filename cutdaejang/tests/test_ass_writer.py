from pathlib import Path

from cutdaejang.core.render_engine.ass_writer import ass_color, escape_ass_text, write_ass
from tests.test_spec import make_valid_spec


def test_ass_color_bgr_order():
    assert ass_color("#FFFFFF") == "&H00FFFFFF"
    assert ass_color("#FF8000") == "&H000080FF"  # RGB → BGR
    assert ass_color("#000000", alpha=0x80) == "&H80000000"


def test_escape_blocks_override_tags():
    assert escape_ass_text("a{b}c") == r"a\{b\}c"
    assert escape_ass_text("줄1\n줄2") == r"줄1\N줄2"
    assert r"\N" not in escape_ass_text("경로\\Nasty")[:3]  # \ 뒤 ZWSP로 무력화


def test_write_ass_structure(tmp_path):
    spec = make_valid_spec()
    out = tmp_path / "subs.ass"
    write_ass(spec, out)
    text = out.read_text(encoding="utf-8")

    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    # 폰트 별칭: 스펙 파일명 스타일 → 폰트 패밀리명
    assert "Pretendard ExtraBold" in text
    assert "Pretendard-ExtraBold" not in text.split("[Events]")[0]
    # 외곽선 3, 하단 중앙 정렬(2)
    style_line = next(l for l in text.splitlines() if l.startswith("Style:"))
    fields = style_line.split(",")
    assert fields[16] == "3" and fields[18] == "2"
    # Dialogue 시간 변환
    assert "Dialogue: 0,0:00:00.30,0:00:02.00,Default,,0,0,0,,첫 문장" in text
    assert "Dialogue: 0,0:00:02.25,0:00:04.40,Default,,0,0,0,,둘째 문장" in text


def test_write_ass_hook_title(tmp_path):
    spec = make_valid_spec()
    spec.hook = "AI가 대신 써준다?\n블로그 자동화 꿀팁!"
    out = tmp_path / "subs.ass"
    write_ass(spec, out)
    text = out.read_text(encoding="utf-8")
    # Title 스타일 정의 존재 + 상단(Alignment 8)
    title_style = next(l for l in text.splitlines() if l.startswith("Style: Title,"))
    assert title_style.split(",")[18] == "8"
    # 영상 전체 구간 고정 표시 + 줄바꿈 \N
    title_ev = next(l for l in text.splitlines() if "Title,," in l)
    assert "0:00:00.00,0:00:05.00" in title_ev
    assert r"블로그 자동화 꿀팁!" in title_ev and r"\N" in title_ev


def _style_line(text, name):
    return next(l for l in text.splitlines() if l.startswith(f"Style: {name},"))


def test_write_ass_hook_band_default_on(tmp_path):
    # 기본값 hook_band=True → 상단 제목이 배경 띠(BorderStyle=3)
    spec = make_valid_spec()
    spec.hook = "썸네일 제목"
    write_ass(spec, tmp_path / "a.ass")
    title = _style_line((tmp_path / "a.ass").read_text(encoding="utf-8"), "Title")
    assert title.split(",")[15] == "3"          # BorderStyle 15번 필드


def test_wrap_text_two_lines():
    from cutdaejang.core.render_engine.ass_writer import wrap_text

    out = wrap_text("오늘은 우리 동네 라멘 맛집에 다녀왔는데 정말 맛있었어요", 16)
    assert out.count("\n") == 1                       # 2줄로 나뉨
    assert wrap_text("짧다", 16) == "짧다"             # 짧으면 그대로
    assert "\n" not in wrap_text("아주 긴 문장인데 끄면 그대로 나온다", 0)  # 0=끔
    assert wrap_text("이미\n줄바꿈", 16) == "이미\n줄바꿈"  # 이미 줄바꿈 있으면 유지


def test_dialogue_wraps_plain_long_text():
    from cutdaejang.core.render_engine.ass_writer import dialogue_text
    from cutdaejang.spec import Style, Subtitle

    st = Style(fade=False, wrap_chars=12)
    body = dialogue_text(Subtitle("아주 긴 자막 문장이라서 두 줄로 나뉘어야 한다", 0, 1_000_000), st)
    assert "\\N" in body                              # ASS 줄바꿈 들어감


def test_colorize_markup_multi_color():
    from cutdaejang.core.render_engine.ass_writer import colorize_markup

    out = colorize_markup("[노랑]월급 3배[/] 밥값은 [빨강]절반?![/]", "#FFFFFF")
    assert out is not None
    assert out.count("\\1c") == 4                 # 색 2개 * (적용+복원)
    assert "월급 3배" in out and "절반?!" in out
    # 마크업 없으면 None (기존 로직으로 폴백)
    assert colorize_markup("그냥 텍스트", "#FFFFFF") is None
    # 아는 색이 하나도 없으면 마크업 취급 안 함 → 원문 유지([참고] 같은 대괄호 보존)
    assert colorize_markup("[없는색]가나[/]", "#FFFFFF") is None
    # 안 닫힌 태그는 줄 끝(또는 다음 색)까지 적용 + '색' 접미 허용
    assert "\\1c" in colorize_markup("[노랑]사진만 넣으면 끝", "#FFFFFF")
    assert "\\1c" in colorize_markup("[노란색]강조[/]", "#FFFFFF")
    assert colorize_markup("[노랑]앞[빨강]뒤", "#FFFFFF").count("\\1c") >= 4


def test_dialogue_text_uses_markup():
    from cutdaejang.core.render_engine.ass_writer import dialogue_text
    from cutdaejang.spec import Style, Subtitle

    st = Style(primary_color="#FFFFFF", fade=False)
    body = dialogue_text(Subtitle("[초록]초록말[/] 흰말", 0, 1_000_000), st)
    assert "\\1c" in body and "초록말" in body


def test_hook_auto_highlights_number():
    from cutdaejang.core.render_engine.ass_writer import hook_dialogue_text
    from cutdaejang.spec import Style

    st = Style(highlight_color="#FFD400")
    # | 없이도 숫자(30개)가 강조색으로 자동 적용
    out = hook_dialogue_text("월 30개 글도 거뜬!\n블로그 자동화 비법", st)
    assert "30개" in out and "\\1c" in out          # 강조색 인라인 태그
    # 숫자 없으면 강조 없음
    assert "\\1c" not in hook_dialogue_text("블로그 자동화 비법", st)
    # 명시 | 가 우선
    assert "\\1c" in hook_dialogue_text("제목 비법 | 비법", st)


def test_write_ass_band_toggles(tmp_path):
    spec = make_valid_spec()
    spec.style.hook_band = False
    spec.style.band = True                       # 자막은 띠 켬, 제목은 끔
    write_ass(spec, tmp_path / "a.ass")
    text = (tmp_path / "a.ass").read_text(encoding="utf-8")
    assert _style_line(text, "Title").split(",")[15] == "1"    # 제목 띠 끔 → 외곽선
    assert _style_line(text, "Default").split(",")[15] == "3"  # 자막 띠 켬 → 박스


def test_write_ass_no_hook_no_title_event(tmp_path):
    spec = make_valid_spec()  # hook 없음
    out = tmp_path / "subs.ass"
    write_ass(spec, out)
    text = out.read_text(encoding="utf-8")
    assert "Title,," not in text  # 훅 없으면 타이틀 이벤트 없음 (스타일 정의는 있어도 무방)


def test_write_ass_margin_override(tmp_path):
    spec = make_valid_spec()
    spec.style.margin_v = 500
    out = tmp_path / "subs.ass"
    write_ass(spec, out)
    style_line = next(
        l for l in out.read_text(encoding="utf-8").splitlines() if l.startswith("Style:")
    )
    assert style_line.split(",")[21] == "500"


def test_write_ass_scales_to_canvas(tmp_path):
    # 4K(2배) 캔버스 → 자막 크기·여백도 2배 (초고화질에서 절반 크기로 나오던 버그)
    from cutdaejang.spec import Background, Canvas, Style, Subtitle, TimelineSpec

    spec = TimelineSpec(
        canvas=Canvas(w=2160, h=3840, fps=30), duration_us=1_000_000,
        background=Background(type="color", color="#000"),
        subtitles=[Subtitle("가", 0, 500_000)],
        style=Style(size=84, margin_v=480, outline=4),
    )
    write_ass(spec, tmp_path / "a.ass")
    st = next(l for l in (tmp_path / "a.ass").read_text(encoding="utf-8").splitlines()
              if l.startswith("Style: Default")).split(",")
    assert st[2] == "168" and st[21] == "960"


def test_write_ass_hook_scale_multiplies_title_size(tmp_path):
    # 훅 스튜디오 크기 선택(v0.31) — hook_scale 배수가 Title 폰트 크기에 반영
    spec = make_valid_spec()
    spec.hook = "크기 테스트"
    write_ass(spec, tmp_path / "base.ass")
    base = _style_line((tmp_path / "base.ass").read_text(encoding="utf-8"), "Title")
    spec.style.hook_scale = 1.4
    write_ass(spec, tmp_path / "big.ass")
    big = _style_line((tmp_path / "big.ass").read_text(encoding="utf-8"), "Title")
    assert round(int(base.split(",")[2]) * 1.4) == int(big.split(",")[2])


def test_band_seam_fix_two_layer():
    """v0.40.1: 색 강조 줄 + 띠 = 유령 띠(단일 run) + 글자(bord0) 2층 — 이음새 제거."""
    from cutdaejang.core.render_engine.ass_writer import band_event_lines

    colored = "안녕 {\\1c&H00D4FF&}강조{\\1c&HFFFFFF&} 문장"
    lines = band_event_lines("Title", "0:00:00.00", "0:00:03.00", colored,
                             band_on=True, fade=False)
    assert len(lines) == 2
    ghost, text = lines
    assert "\\1a&HFF&" in ghost and "\\1c" not in ghost      # 띠: 글자 투명·색 태그 없음(단일 run)
    assert ghost.startswith("Dialogue: 0,")
    assert text.startswith("Dialogue: 1,") and "\\bord0" in text  # 글자: 위 레이어·박스 없음
    assert "강조" in ghost and "강조" in text                 # 글자 배치는 동일 (박스 폭 일치)

    # 색 없는 줄은 원래도 박스가 한 장 → 그대로 1줄 (이중 그리기 방지)
    plain = band_event_lines("Default", "0:00:00.00", "0:00:03.00", "그냥 자막",
                             band_on=True, fade=False)
    assert len(plain) == 1 and "\\1a" not in plain[0]

    # 띠 꺼짐이면 색이 있어도 1줄
    off = band_event_lines("Default", "0:00:00.00", "0:00:03.00", colored,
                           band_on=False, fade=True)
    assert len(off) == 1

    # 페이드는 유령 띠에도 붙어 띠·글자가 같이 나타남
    faded = band_event_lines("Default", "0:00:00.00", "0:00:03.00",
                             "{\\fad(100,60)}" + colored, band_on=True, fade=True)
    assert "\\fad(100,60)" in faded[0] and "\\1a&HFF&" in faded[0]


def test_pop_anim_two_layer_band(tmp_path):
    """v0.43 자막 팝 — \\t 스케일 태그, 띠는 유령 레이어로 고정(요동 없음)."""
    from cutdaejang.spec import Canvas, Style, Subtitle, TimelineSpec

    spec = TimelineSpec(
        canvas=Canvas(w=1080, h=1920), duration_us=3_000_000,
        style=Style(anim="pop", band=True, fade=True),
        subtitles=[
            Subtitle(text="팝 [노랑]강조[/] 줄", start_us=0, end_us=1_500_000),
            Subtitle(text="색 없는 줄", start_us=1_500_000, end_us=3_000_000),
        ])
    text = Path(write_ass(spec, tmp_path / "pop.ass")).read_text(encoding="utf-8")
    assert "\\t(0,130,\\fscx100" in text
    d = [ln for ln in text.splitlines() if ln.startswith("Dialogue") and ",Default," in ln]
    assert len(d) == 4  # 팝이 있으면 색 유무와 무관하게 두 줄 다 2층(띠+글자)
    ghosts = [ln for ln in d if "\\1a&HFF&" in ln]
    assert ghosts and all("\\fscx" not in g for g in ghosts)  # 띠는 팝 없이 고정

    spec.style.anim = "none"
    text2 = Path(write_ass(spec, tmp_path / "nopop.ass")).read_text(encoding="utf-8")
    assert "\\t(0,130" not in text2


def test_hook_style_presets(tmp_path):
    """v0.52 상단 제목 프리셋 — 색·테두리·띠·글로우가 스타일별로 갈리는지."""
    from cutdaejang.spec import Canvas, Style, Subtitle, TimelineSpec

    def build(hook_style):
        spec = TimelineSpec(
            canvas=Canvas(w=1080, h=1920), duration_us=2_000_000,
            hook="충격 3가지 사실",
            style=Style(hook_style=hook_style, hook_band=True),
            subtitles=[Subtitle(text="본문", start_us=0, end_us=2_000_000)])
        return Path(write_ass(spec, tmp_path / f"{hook_style}.ass")).read_text(encoding="utf-8")

    base = build("기본")
    title = next(ln for ln in base.splitlines() if ln.startswith("Style: Title"))
    assert "&H00FFFFFF" in title and ",3," in title      # 흰 글자 + 띠(BorderStyle 3)

    fun = build("예능 노랑")
    t2 = next(ln for ln in fun.splitlines() if ln.startswith("Style: Title"))
    assert "&H0000D4FF" in t2                            # FFD400 → BGR 00D4FF
    assert "&H00101010" in t2 and ",1," in t2            # 검정 테두리, 띠 없음(프리셋 강제)

    box = build("화이트 박스")
    t3 = next(ln for ln in box.splitlines() if ln.startswith("Style: Title"))
    assert "&H00141414" in t3 and "&H00F2F2F2" in t3     # 검정 글자 + 흰 띠

    neon = build("네온")
    hook_ev = next(ln for ln in neon.splitlines()
                   if ln.startswith("Dialogue") and ",Title," in ln)
    assert "\\blur" in hook_ev                           # 글로우
    t4 = next(ln for ln in neon.splitlines() if ln.startswith("Style: Title"))
    assert "&H00F0FF9C" in t4                            # 9CFFF0 → BGR F0FF9C

    # 강조 복원색이 프리셋 기본색을 따라감 (화이트 박스에서 흰색 복원이면 안 보임)
    spec = TimelineSpec(canvas=Canvas(w=1080, h=1920), duration_us=2_000_000,
                        hook="제목 | 제목", style=Style(hook_style="화이트 박스"),
                        subtitles=[Subtitle(text="x", start_us=0, end_us=1_000_000)])
    text = Path(write_ass(spec, tmp_path / "hl.ass")).read_text(encoding="utf-8")
    ev = next(ln for ln in text.splitlines() if ",Title," in ln and "\\1c" in ln)
    assert "\\1c&H141414&" in ev                         # 복원 = 프리셋 검정
