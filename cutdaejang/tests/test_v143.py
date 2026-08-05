"""v1.43 — 목록 85 ①~⑤: 초보자 첫인상 5종.

85번 전체 점검(675ca54)에서 실측으로 확인한 것:
  · 첫 설치가 «자세히 모드»로 열린다 — 제일 복잡한 화면을 제일 먼저 만난다
  · 쉬운 모드 켜는 법을 모르면 영영 모른다 (위 바 버튼은 스크롤하면 사라짐)
  · 카드 안에서 ⚙ 문이 둘 (위 바 + 고정 바) — 72번에서 세운 «문 하나» 원칙 위반
  · 보이는 글자에 TTS·Whisper·프롬프트·브루식·몽타주·덕킹·재렌더
  · 「대본 따오기」는 눌러 보기 전엔 뜻을 모른다

주의 — 점검 문서의 «쉬운 모드에도 30~50개 남음» 수치는 과대집계였다.
정적 HTML만 세서 EASY_HIDE_IDS(런타임 다이어트)를 놓쳤던 것. 실제 구멍은
접힘상자 «밖» + EASY_HIDE_IDS «밖»의 7개뿐이고, 이번에 그 7개를 넣었다.
"""

import re

from cutdaejang import __version__
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))

# 사용자 «눈에 보이는» 글자만 — script·style·HTML주석 제거 (속성은 남김: 툴팁도 보인다)
VIS = re.sub(r"<script>.*?</script>", "", HTML, flags=re.S)
VIS = re.sub(r"<style>.*?</style>", "", VIS, flags=re.S)
VIS = re.sub(r"<!--.*?-->", "", VIS, flags=re.S)


def test_version():
    assert __version__ == "1.43.0"


# ── ① 처음 설치는 쉬운 모드 ─────────────────────────────────────
def test_fresh_install_boots_into_easy_mode():
    """🔴 저장값이 «없으면» 쉬운 모드 — 할아버지가 첫 화면에서 만나는 기본값."""
    assert "const _em = ((s || {}).ui || {}).easy_mode;" in JS
    assert "applyEasy(_em == null ? true : !!_em);" in JS
    # 옛 무조건 강제(!! 강변환)는 사라져야 한다 — 남으면 기본이 다시 «자세히»
    assert "applyEasy(!!(((s || {}).ui || {}).easy_mode));" not in JS


def test_saved_choice_is_respected():
    """한 번이라도 직접 껐으면 계속 꺼져 있어야 한다 — 강제 아님."""
    # 토글이 켬/끔 «양쪽 다» bool로 저장하고 (truthy만 저장하면 끔이 부활한다)
    assert "JSON.stringify({patch: {ui: {easy_mode: on}}})" in JS
    # 서버가 bool을 그대로 받아 준다
    assert 'isinstance(ui_p.get("easy_mode"), bool)' in SRC


def test_easy_banner_offers_a_way_out():
    """🔴 «전부 보기»가 띠 안에 있어야 한다 — 위 바는 스크롤하면 사라진다."""
    seg = HTML.split('id="easyBar"')[1].split("</div>")[0]
    assert 'onclick="toggleEasy(event)"' in seg
    assert "전부 보기" in seg
    assert "쉬운 모드" in seg                      # 지금 어떤 상태인지 이름을 말해준다


# ── ② 쉬운 모드 2차 다이어트 ────────────────────────────────────
def test_second_diet_covers_the_stragglers():
    """접힘상자 «밖»이라 쉬운 모드에서도 보이던 7개가 목록에 들어갔는지."""
    arr = JS.split("const EASY_HIDE_IDS = [")[1].split("];")[0]
    for _id in ("genSpeedSel", "photoSec", "secTempoSel", "secBgmSel",
                "secXfadeSel", "secQualitySel", "vpVol"):
        assert f"'{_id}'" in arr, _id
        assert f'id="{_id}"' in HTML, f"{_id} — 목록이 유령 id를 가리킴"


# ── ③ ⚙ 문 하나 ────────────────────────────────────────────────
def test_only_one_settings_door_inside_cards():
    """카드 안 = 고정 바 ⚙만, 첫 화면 = 위 바 ⚙만 (같은 방에 문 둘 금지)."""
    assert 'id="topSet"' in HTML
    assert 'id="navSet"' in HTML
    nav = JS.split("function updateNav(")[1].split("\nfunction ")[0]
    assert "ts.classList.toggle('hidden', !!info)" in nav
    # 고정 바 자체는 반대 방향 (첫 화면에서 숨김) — 둘이 겹치는 순간이 없다
    assert "bar.classList.toggle('hidden', !info)" in nav


# ── ④ 보이는 전문용어 → 우리말 ─────────────────────────────────
def test_visible_jargon_is_gone():
    """🔴 눌러 보기 전에 읽고 이해가 돼야 한다 — 화면 글자에서 은어 제거."""
    for bad in ("목소리(TTS)를 만들어", "TTS 한 문장", "TTS 오독", "분당 TTS 호출",
                "TTS 한도", "(Whisper 자막 추천)", "정확도(Whisper 모델)",
                "편집·Whisper 자막", "프롬프트만 뽑기", "프롬프트 전체 복사",
                "(브루식", "몽타주", "재렌더", "BGM 덕킹"):
        assert bad not in VIS, f"화면에 아직 남음: {bad}"


def test_plain_korean_replacements_exist():
    """지우기만 하면 안 된다 — 같은 자리에서 우리말이 설명해야 한다."""
    for good in ("분당 목소리 호출 한도", "무료 음성인식", "장면 설명만 뽑기",
                 "장면 설명 전체 복사 (통합)", "말할 때 배경음악 줄이기",
                 "다시 만들면 동일", "읽는 한 문장", "잘못 읽는 것 방지"):
        assert good in VIS, good
    # 배속 셀렉트 라벨은 JS가 런타임에 만든다 — 거기서도 은어를 걷어냈는지
    assert "컷: 자동 (핵심만 이어붙임)" in JS
    assert "컷: 자동 (핵심 몽타주)" not in JS


def test_terms_worth_teaching_stay_in_parentheses():
    """검색·질문에 쓰는 용어는 괄호로 가르친다 — «우리말 먼저 (용어)» 꼴."""
    assert "장면 설명(프롬프트)" in VIS
    assert '<span class="hint">(TTS)</span>' in VIS
    assert '<span class="hint">(덕킹)</span>' in VIS


# ── ⑤ 「대본 따오기」 → 뜻이 보이는 이름 ─────────────────────────
def test_rip_button_says_what_it_does():
    assert "🎙→📃" not in HTML                    # 옛 화살표 이름은 전부 청산
    assert HTML.count("🎙 영상 속 말 받아적기") >= 3   # 첫 화면 버튼·NAV_INFO·전용 화면
    seg = HTML.split('onclick="openRip(event)"')[1][:300]
    assert "받아 적어 드려요" in seg              # 버튼 툴팁이 한 문장으로 설명


def test_old_name_stays_as_subtitle():
    """차수 문서·게시글에 «대본 따오기»로 안내한 이력 — 부제로 남겨 잇는다."""
    assert "(대본 따오기)" in HTML


def test_job_list_uses_the_new_name():
    """만들기 목록에 찍히는 작업 제목도 같은 이름이어야 헷갈리지 않는다."""
    assert 'title="🎙 영상 속 말 받아적기"' in SRC
    assert 'title="🎙→📃' not in SRC


# ── 화면이 여전히 성한가 ───────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label", "span"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
