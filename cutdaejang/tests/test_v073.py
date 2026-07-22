"""v0.73 — 다색 팝 자막/훅 프리셋(문장마다 색 회전 + 흰 테두리) + 블랙 박스 + 빠른 템포.

사용자 요청: miracle.mom_ 릴스처럼 자막이 문장마다 색이 바뀌고 굵은 흰 테두리가 있는
스타일 + 검은 박스 제목 + 빠른 편집 템포. 수동 [색] 마크업 없이 원클릭으로.
"""

import re

from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.spec import TimelineSpec, Canvas, Style, Subtitle


# ── 1) 프리셋이 등록돼 있다 ──────────────────────────────────────────────
def test_presets_registered():
    assert "다색 팝" in aw.SUB_STYLES and "다색 팝" in aw.HOOK_STYLES
    assert "블랙 박스" in aw.SUB_STYLES and "블랙 박스" in aw.HOOK_STYLES
    assert aw.SUB_STYLES["다색 팝"].get("pop_rotate") is True
    assert aw.SUB_STYLES["다색 팝"].get("outline_color") == "#FFFFFF"  # 흰 테두리
    assert aw.SUB_STYLES["블랙 박스"].get("band") is True              # 검은 띠
    assert len(aw.POP_PALETTE) >= 5                                    # 회전할 색이 충분


# ── 2) dialogue_text: pop_color가 문장 전체를 칠한다 (마크업·강조 우선순위 유지) ──
def _sub(text, hl=""):
    return Subtitle(text=text, start_us=0, end_us=1_000_000, highlight=hl)


def test_pop_color_colors_whole_line():
    style = Style()
    body = aw.dialogue_text(_sub("벌써 포기했을 거예요"), style, pop_color="#FF3B30")
    assert body.startswith("{\\1c" + aw._inline_color("#FF3B30") + "}")
    assert "벌써" in body and "거예요" in body


def test_manual_markup_beats_pop_color():
    # 사용자가 직접 [민트]...[/] 쓰면 pop_color 무시하고 그 색 존중
    style = Style()
    body = aw.dialogue_text(_sub("[민트]직접색[/] 나머지"), style, pop_color="#FF3B30")
    assert aw._inline_color("#31E1C4") in body        # 민트가 들어감
    # 문장 시작이 pop 빨강 프리픽스로 덮이지 않음
    assert not body.startswith("{\\1c" + aw._inline_color("#FF3B30") + "}")


def test_no_pop_color_keeps_highlight_behavior():
    style = Style(highlight_color="#FFD400")
    body = aw.dialogue_text(_sub("핵심은 습관", hl="습관"), style)  # pop 없음
    assert aw._inline_color("#FFD400") in body        # 강조 단어만 노랑


# ── 3) hook_dialogue_text: pop_color가 제목 전체를 칠한다 ────────────────────
def test_hook_pop_color():
    style = Style()
    body = aw.hook_dialogue_text("포기하는 것도 습관", style, pop_color="#FF3B30")
    assert body.startswith("{\\1c" + aw._inline_color("#FF3B30") + "}")


def test_hook_pipe_beats_pop():
    style = Style(highlight_color="#FFD400")
    body = aw.hook_dialogue_text("제목 | 강조", style, highlight="#FFD400", pop_color="#FF3B30")
    # 파이프 강조가 우선 — 전체를 빨강으로 덮지 않음
    assert not body.startswith("{\\1c" + aw._inline_color("#FF3B30") + "}")


# ── 4) write_ass: 문장마다 색이 회전 + 흰 테두리 + 검은 박스 ──────────────────
def _render(sub_style, n=4, hook_style="기본"):
    subs = [Subtitle(text=f"문장{i}", start_us=i * 10 ** 6, end_us=(i + 1) * 10 ** 6)
            for i in range(n)]
    style = Style(sub_style=sub_style, hook_style=hook_style)
    spec = TimelineSpec(canvas=Canvas(1080, 1920, 30), hook="제목입니다",
                        subtitles=subs, style=style, duration_us=n * 10 ** 6)
    import tempfile
    p = tempfile.mktemp(suffix=".ass")
    aw.write_ass(spec, p)
    return open(p, encoding="utf-8").read()


def test_pop_rotates_colors_per_sentence():
    txt = _render("다색 팝", n=4)
    # 자막(Default) 이벤트의 인라인 색 4개가 팔레트 앞 4색과 일치
    ev = [l for l in txt.splitlines() if l.startswith("Dialogue") and ",Default," in l]
    cols = [re.search(r"\\1c(&H[0-9A-F]{6}&)", l).group(1) for l in ev]
    expect = [aw._inline_color(c) for c in aw.POP_PALETTE[:4]]
    assert cols == expect, (cols, expect)
    # Default 스타일 OutlineColour가 흰색
    dstyle = [l for l in txt.splitlines() if l.startswith("Style: Default")][0]
    assert "FFFFFF" in dstyle.split(",")[5]


def test_pop_hook_uses_first_palette_color():
    txt = _render("기본", n=2, hook_style="다색 팝")
    hook_ev = [l for l in txt.splitlines() if l.startswith("Dialogue") and ",Title," in l][0]
    assert aw._inline_color(aw.POP_PALETTE[0]) in hook_ev


def test_black_box_is_band():
    txt = _render("블랙 박스", n=2)
    dstyle = [l for l in txt.splitlines() if l.startswith("Style: Default")][0]
    # 포맷: Name,Font,Size,Primary,Secondary,Outline,Back,B,I,U,S,ScaleX,ScaleY,
    #       Spacing,Angle,BorderStyle(15),Outline(16),Shadow,... → 띠=BorderStyle 3
    fields = dstyle.split(",")
    assert fields[15].strip() == "3"                  # BorderStyle=3 (불투명 박스)
    assert int(fields[16]) > 3                        # 박스 두께(sc(18)) — 띠 렌더 확인


# ── 5) 빠른 템포 → 몽타주 조각 길이(piece_us) 매핑 (webui 공식 복제) ───────────
def _piece(tempo):
    return {"빠르게": 2_400_000, "아주 빠르게": 1_700_000}.get(str(tempo or ""), 3_500_000)


def test_tempo_piece_mapping():
    assert _piece("") == 3_500_000          # 기본
    assert _piece("빠르게") == 2_400_000     # 촘촘
    assert _piece("아주 빠르게") == 1_700_000  # 더 촘촘
    assert _piece("이상한값") == 3_500_000    # 알 수 없으면 기본


def test_spread_ranges_more_cuts_when_faster():
    from cutdaejang.core import edit_mode
    total, target = 60_000_000, 30_000_000
    base = edit_mode.spread_ranges(total, target, piece_us=3_500_000)
    fast = edit_mode.spread_ranges(total, target, piece_us=1_700_000)
    assert len(fast) > len(base)            # 조각이 짧으면 컷이 더 많다


# ── 6) UI: 프리셋 옵션·템포 셀렉트·전송/기억 배선 ──────────────────────────
def test_html_has_pop_and_blackbox_and_tempo():
    from cutdaejang.gui import webui
    html = webui._HTML
    # 4개 스타일 드롭다운 모두에 두 옵션이 들어감
    assert html.count('value="다색 팝"') >= 4
    assert html.count('value="블랙 박스"') >= 4
    # 빠른 템포 셀렉트
    assert 'id="editTempoSel"' in html
    assert 'value="빠르게"' in html and 'value="아주 빠르게"' in html
    # 전송 바디 + 기억 키
    assert "tempo:" in html
    assert "tempo" in webui._EDIT_LAST_KEYS


def test_backend_wires_tempo_to_montage():
    import inspect

    from cutdaejang.gui import webui
    src = inspect.getsource(webui._run_edit)
    assert 'params.get("tempo")' in src
    assert "piece_us=_piece" in src
