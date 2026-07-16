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
