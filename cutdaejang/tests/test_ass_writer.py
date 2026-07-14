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
