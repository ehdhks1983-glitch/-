"""v1.12 — 회원님 요청 4종.

  ①② 쇼핑 사진 0장의 **진짜 원인**: 로그인한 브라우저가 아니라 빈 임시 프로필로
      헤드리스를 띄워, 쿠팡·네이버가 사진 없는 축약 페이지만 줬다.
      → [🌐 내 크롬 열기]로 전용 프로필에 한 번 로그인 → 수집은 그 복제본으로.
      (회원님 블로그 퍼블리셔가 쓰는 방식과 같다. 본인 브라우저·본인 로그인이라
       봇 차단 우회가 아니다.)
  ⑮ 무료 음원 14곡 → 50곡+ (분위기 13종)
  ⑯ 업로드 키트 제목이 다 비슷하던 문제 — 공식 8종 강제 배분 + 플랫폼별 제목 분리
     + 최근에 쓴 제목과 겹침 방지
  ⑰ 쇼츠 위아래 후킹 띠 — **기존 훅 방식은 그대로 두고** 새 스타일만 추가
"""

import inspect
import re

from cutdaejang import __version__
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui
from cutdaejang.spec import Background, Canvas, Style, Subtitle, TimelineSpec
from cutdaejang.tools import fetch_bgm, product_page as pp


def test_version():
    assert __version__ == "1.33.0"


# ── ①② 쇼핑: 로그인한 브라우저로 수집 ──────────────────────────
def test_login_profile_is_separate_and_used_for_collection():
    prof = pp.login_profile_dir()
    assert "cutdaejang" in str(prof)          # 회원님 평소 크롬 프로필을 건드리지 않음
    args = pp._browser_args("chrome", "https://x")
    prof_arg = next(a for a in args if a.startswith("--user-data-dir="))
    assert prof_arg.split("=", 1)[1]          # 항상 전용 프로필 (기존 보장 유지)
    assert "--headless=new" in args


def test_collect_profile_falls_back_when_never_logged_in():
    """로그인해 둔 적이 없으면 예전처럼 빈 임시 프로필 — 동작이 안 바뀐다."""
    assert "cutdaejang_headless" in pp._collect_profile()


def test_logged_in_hosts_is_safe_without_profile():
    assert pp.logged_in_hosts() == []          # 프로필 없음 → 빈 목록, 예외 없음


def test_open_login_browser_reports_when_no_browser(monkeypatch):
    monkeypatch.setattr(pp, "_browser_candidates", lambda: [])
    why = pp.open_login_browser()
    assert "크롬" in why and why                # 조용히 실패하지 않고 이유를 돌려준다


def test_shop_login_ui_and_routes():
    html = webui._apply_links(webui._HTML)
    assert 'id="shopLoginState"' in html
    assert "openShopLogin" in html and "refreshShopLogin" in html
    assert "로그인한 브라우저" in html          # 왜 필요한지 화면에서 설명
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert '"/api/shop_login"' in src and '"/api/shop_login_open"' in src


def test_frontend_accepts_short_links():
    """화면 쪽 상품 링크 검사에도 짧은 주소가 있어야 링크 수집 흐름을 탄다."""
    html = webui._HTML
    m = re.search(r"const SHOP_HOST_RE = /([^/]+)/i;", html)
    assert m and "naver" in m.group(1)
    pattern = m.group(1).replace("\\\\.", ".")
    assert re.search(pattern, "https://naver.me/xUZ6uTko", re.I)
    assert re.search(pattern, "https://link.coupang.com/a/abc", re.I)


def test_new_link_clears_old_product_text():
    """링크로 새로 수집할 때 지난 상품 글이 남아 혼동되지 않게."""
    body = webui._HTML.split("async function makeShopScript")[1][:1400]
    assert "if(linkOnly){" in body and "clearShopPhotos" in body


# ── ⑰ 위아래 띠 (기존 유지 + 추가) ───────────────────────────
def _ass(hook: str, hook_style: str) -> str:
    import pathlib
    import tempfile

    spec = TimelineSpec(
        canvas=Canvas(w=1080, h=1920, fps=30), style=Style(hook_style=hook_style),
        hook=hook, subtitles=[Subtitle(text="문장", start_us=0, end_us=1_000_000)],
        duration_us=5_000_000, background=Background())
    out = pathlib.Path(tempfile.mkdtemp()) / "a.ass"
    aw.write_ass(spec, out)
    return out.read_text(encoding="utf-8")


def test_frame_style_draws_two_bands_and_texts():
    t = _ass("GPT 상세페이지 // AI로 시간은 줄이고, 퀄리티는 올리세요!", "위아래 띠")
    assert t.count("\\p1\\bord0\\shad0") == 2          # 위·아래 띠 2개
    assert "퀄리티는 올리세요" in t                     # 아래 띠 문구
    assert "\\fs" in t.split("Dialogue: 4")[1][:120]   # 초대형 제목


def test_frame_style_without_bottom_text_still_frames():
    t = _ass("제목만 있음", "위아래 띠")
    assert t.count("\\p1\\bord0\\shad0") == 2
    assert "//" not in t


def test_existing_hook_styles_untouched():
    """회원님 요청: 기존 것은 그대로. 다른 스타일엔 띠가 생기면 안 된다."""
    for st in ("기본", "예능 노랑", "블랙 박스", "네온"):
        t = _ass("일반 훅 제목", st)
        assert "\\p1\\bord0\\shad0" not in t, st
        assert ",Title,," in t                          # 기존 훅은 그대로 나온다


def test_frame_style_is_offered_in_ui():
    html = webui._apply_links(webui._HTML)
    assert html.count('value="위아래 띠"') == 2          # 편집·생성 두 폼
    assert "//" in html and "아래 띠" in html            # 쓰는 법 안내


def test_two_line_wrap_picks_middle_space():
    assert aw._wrap_two_lines("한글 제목 두줄로", 4).count("\\N") == 1
    assert "\\N" not in aw._wrap_two_lines("짧다", 9)


# ── ⑯ 업로드 키트 다양성 ─────────────────────────────────────
def test_title_formulas_expanded_and_labeled():
    p = sg.UPLOAD_KIT_PROMPT
    assert "정확히 8개" in p
    for kind in ("검색형", "숫자·결과형", "궁금증형", "타깃 호명형",
                 "역설·반전형", "경고·실수형", "비교형", "후기·경험형"):
        assert kind in p, kind
    assert "title_kinds" in p
    assert "첫 두 어절이 서로 겹치면 안 된다" in p


def test_platform_titles_are_separate():
    p = sg.UPLOAD_KIT_PROMPT
    assert "tiktok.title" in p and "instagram.title" in p
    assert "유튜브 제목을 그대로 쓰지 말 것" in p
    kit = sg.normalize_kit({"titles": ["t"] * 9, "title_kinds": ["검색", "숫자"],
                            "tiktok": {"title": "짧은 훅"},
                            "instagram": {"title": "감성 훅"}})
    assert len(kit["titles"]) == 8
    assert kit["title_kinds"] == ["검색", "숫자"]
    assert kit["tiktok"]["title"] == "짧은 훅"
    assert kit["instagram"]["title"] == "감성 훅"


def test_recent_titles_go_into_the_prompt():
    assert "{recent}" in sg.UPLOAD_KIT_PROMPT
    sig = inspect.signature(sg.suggest_upload_kit)
    assert "recent_titles" in sig.parameters
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "recent_titles=[str(r.get(\"title\") or \"\")" in src


# ── ⑮ 무료 음원 ─────────────────────────────────────────────
def test_bgm_library_expanded():
    assert len(fetch_bgm.TRACKS) >= 50
    titles = [t for _, t in fetch_bgm.TRACKS]
    assert len(titles) == len(set(titles)), "같은 곡이 두 번 들어갔다"
    moods = {m for m, _ in fetch_bgm.TRACKS}
    for want in ("감동", "긴장", "시네마틱", "로파이", "트렌디", "뉴스·리뷰"):
        assert want in moods, want
    # 파일명이 윈도우에서 안전해야 한다 (금지문자 없음)
    for mood, title in fetch_bgm.TRACKS:
        name = fetch_bgm.save_name(mood, title)
        assert not set(name) & set('\\/:*?"<>|'), name


def test_bgm_failures_are_explained(tmp_path):
    ok, fail = fetch_bgm.main(bgm_dir=tmp_path, fetch_fn=lambda url, dest: False)
    assert not ok and len(fail) == len(fetch_bgm.TRACKS)
    src = inspect.getsource(fetch_bgm.main)
    assert "못 받은 곡" in src and "재시도" in src
