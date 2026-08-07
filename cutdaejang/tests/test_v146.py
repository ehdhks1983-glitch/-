"""v1.46 — 목록 91(클립 챌린지 카운팅) + 92(링크 궁합 안내) + 93(사진 추가).

회원님 45차:
> "네이버 클립 등록할 때 내가 준 글을 기반으로 바꿔야 할 것 같아"
>   (오늘 클립 챌린지 카운팅 = #오늘클립챌린지 + 내용에 맞는 «인정»
>    정보태그 + 전체 공개 — 뉴스·블로그·오픈톡 정보태그는 미션 제외)
> "블로그 글로 만들기에서 유튜브 넣으면 대본을 가져오고 뉴스 넣으면
>  크롤링이 안 되는데 이 부분도 같이 강조를 해주고"
> "사진 크롤링이 안 되는 곳도 있으니 사진 첨부 기능 추가해줘"

93에서 발견한 잠재 사고 하나: 기존 쇼핑 접힘상자의 사진 픽커가 긁어온
사진 배열을 «통째로 덮어써서», 블로그에서 가져온 사진이 조용히 사라질 수
있었다 — 합치기(+중복 제거)로 고쳤다.
"""

import re

from cutdaejang import __version__
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.50.0"


# ── 91 네이버 클립 챌린지 카운팅 ────────────────────────────────
def test_kit_text_includes_challenge_checklist():
    """통합 복사 텍스트에 카운팅 3조건이 그대로 — 회원님이 정리한 규칙."""
    kit = {"naver_clip": {"title": "오디세이 결말 해석", "tags": ["영화리뷰", "오디세이"]},
           "checklist": ["썸네일 확인"]}
    txt = webui._kit_text(kit, "오디세이 결말")
    assert "#영화리뷰 #오디세이 #오늘클립챌린지" in txt, "필수 태그 자동 포함"
    assert "카운팅 3조건" in txt
    assert "정보태그" in txt and "전체 공개로 발행" in txt
    assert "뉴스·블로그·오픈톡 정보태그는 미션 제외" in txt
    assert "일반 클립으로 올리세요" in txt, "맞는 정보태그 없으면 억지로 붙이지 말라"
    assert "활동 내역" in txt, "반영 확인법"
    assert "바뀔 수 있어요" in txt, "네이버 규칙 변동 유의 — 단정하지 않는다"


def test_kit_without_naver_clip_stays_clean():
    txt = webui._kit_text({"checklist": []}, "제목")
    assert "#오늘클립챌린지" not in txt, "네이버 클립 구역이 없으면 안 낀다"


# ── 92 링크 궁합 안내 ───────────────────────────────────────────
def test_intro_explains_what_each_link_type_gives():
    seg = HTML.split('id="weblinkCard"')[1][:3000]
    assert "네이버 블로그</b> — 사진·본문을 다 가져와요" in seg
    assert "유튜브 링크</b> — 짧은 설명글만" in seg
    assert "긁기를 막는 곳" in seg, "뉴스·쇼핑몰 차단 안내"
    assert "[📁 사진 추가]" in seg, "대안까지 같은 자리에서"


def test_zero_photo_result_points_to_attach():
    seg = JS.split("function applyWeblink(")[1].split("\nasync function ")[0]
    assert "사진을 못 가져오는 곳이에요" in seg
    assert "if(!imgs.length)" in seg


# ── 93 사진 추가 ────────────────────────────────────────────────
def test_photo_add_button_lives_in_the_main_flow():
    """쇼핑 접힘상자 «안»이 아니라 ② 사진 확인에 상시로 보여야 한다."""
    seg = HTML.split("사진 확인")[1].split('id="wlGrid"')[0]
    assert "addWlPhotos(event)" in seg
    assert "📁 사진 추가 (여러 장)" in seg


def test_added_photos_merge_not_overwrite():
    """🔴 긁어온 사진을 덮어쓰면 조용히 사라진다 — 합치고 중복은 거른다."""
    assert "function _wlMergePhotos(" in JS
    seg = JS.split("function _wlMergePhotos(")[1].split("\nasync function ")[0]
    assert "new Set(r.images)" in seg, "중복 제거"
    assert "r.images.push(p)" in seg and "r.previews.push('')" in seg
    # 옛 픽커(쇼핑 접힘상자)의 덮어쓰기 잔재가 없어야 한다
    assert "window._weblink.images = paths;" not in JS
    old = JS.split("async function pickWlPhotos(")[1].split("\nasync function ")[0]
    assert "_wlMergePhotos(paths)" in old, "옛 픽커도 합치기 경유"


def test_grid_renders_local_photos_without_preview():
    """내 사진은 서버 미리보기가 없다 — 이름표(📁)로 그리되 번호 체계는 하나로."""
    assert "function renderWlGrid(" in JS
    seg = JS.split("function renderWlGrid(")[1].split("\nfunction ")[0]
    assert "(r.images || []).forEach" in seg, "previews가 아니라 images 기준 (내 사진 포함)"
    assert "cb.dataset.i = i" in seg, "만들기 페이로드의 체크 번호와 1:1"
    assert "String.fromCharCode(92)" in seg, "윈도 경로 이름표 (역슬래시 무사용 규약)"
    # applyWeblink는 그리드를 함수로 그린다 (인라인 중복 없음)
    ap = JS.split("function applyWeblink(")[1].split("\nasync function ")[0]
    assert "renderWlGrid();" in ap
    assert "window._weblink = r;" in ap, "그리드·만들기가 같은 근원을 본다"


def test_start_still_filters_by_checkbox():
    """추가한 사진도 체크 해제로 뺄 수 있어야 한다 — 기존 배선 유지 확인."""
    seg = JS.split("async function startWeblink(")[1].split("\nasync function ")[0]
    assert "window._weblink" in seg
    assert 'data-i="' in seg.replace("' + i + '", '"')  # 체크 번호로 거른다


# ── 화면이 여전히 성한가 ───────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label", "span"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
