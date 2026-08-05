"""v1.37 — 목록 74(끌어서 구간 정하기) · 75(자막이 말 한가운데서 끊기던 것).

회원님 34차 ①:
> "이 기능을 넣는 게 좋을지 조사" (경쟁 프로그램 화면 2장)

조사해 보니 그쪽에만 있고 우리에게 없는 건 «끌어서 구간 잡기» 하나였다.
우리는 숫자를 손으로 넣거나 [▶ 여기부터] 버튼을 눌러야 했다. 숫자 칸은
정확하지만 «몇 초쯤인지» 감이 안 온다 — 초보자에겐 그게 벽이다.
그래서 띠를 더한다. **숫자 칸은 없애지 않는다** — 정확히 맞추고 싶은
분을 위해 남기고, 둘을 «서로» 연동한다.

회원님 34차 ②:
> "안녕하세요 더브라운호텔입니다 여기가 좋은점은 뭐뭐 입니다
>  이 예시로 봤을 때 «안녕하세요 더브라운호텔입니다» 끊어지고
>  «여기가 좋은점은 뭐뭐입니다» 끊어지고 이런 식으로 돼야 하는데
>  중간에 내려오고 이런 식이라"

원인: 우리는 «문장부호»와 «글자 수»로만 나눴다. 한국어 대본은 마침표 없이
말이 끝나는 경우가 아주 흔하다 → 부호가 없으니 글자 수만 남고, 그러면
말 한가운데서 잘린다. 종결어미를 절 경계로 인정하면 해결된다.
"""

import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.42.0"


# ══ 74: 끌어서 구간 정하기 ═══════════════════════════════════════
def test_the_band_exists_as_one_shared_part():
    """두 곳(긴 영상·편집)이 각자 만들면 한쪽만 고쳐지는 날이 온다."""
    assert JS.count("function bandMake(") == 1
    assert JS.count("function bandPaint(") == 1
    assert JS.count("function bandDrag(") == 1
    for cls in (".rband", ".rb-fill", ".rb-h", ".rb-lab", ".rb-off"):
        assert cls in HTML, cls


def test_dragging_fills_the_number_boxes():
    """🔴 요점 — 끌면 «아래 숫자 칸이 자동으로 채워져야» 한다."""
    body = JS.split("function bandDrag(")[1].split("\n}")[0]
    assert "band._set(s, e)" in body
    sec = JS.split("const band = bandMake({")[1].split("});")[0]
    assert "si.value = fmtMMSS(s); ei.value = fmtMMSS(e);" in sec


def test_the_number_boxes_still_exist_and_drive_the_band_back():
    """숫자 칸을 없애면 «정확히 맞추기»가 사라진다 — 양방향이어야 한다."""
    row = JS.split("function addSectionRow(")[1].split("\nfunction ")[0]
    assert "si.className = 'sec-start'" in row and "ei.className = 'sec-end'" in row
    assert "si.oninput = function(){ bandPaint(band); };" in row
    assert "ei.oninput = function(){ bandPaint(band); };" in row


@pytest.mark.parametrize("fn", ["bs.onclick", "be.onclick"])
def test_the_old_buttons_keep_working_and_repaint(fn):
    """[▶ 여기부터]/[⏹ 여기까지]는 그대로 둔다 — 다만 띠도 따라와야 한다."""
    row = JS.split("function addSectionRow(")[1].split("\nfunction ")[0]
    line = [ln for ln in row.splitlines() if ln.strip().startswith(fn)]
    assert line, fn
    assert "bandPaint(band);" in line[0]


def test_releasing_the_handle_plays_from_there():
    """회원님 요구 — 놓으면 «그 지점부터 바로 재생»해 확인."""
    sec = JS.split("const band = bandMake({")[1].split("});")[0]
    done = sec.split("done: function(")[1]
    assert "p.currentTime = (mode === 's') ? s : Math.max(s, e - 3);" in done, \
        "끝을 옮겼으면 그 앞을 보여줘야 확인이 된다"
    assert "window._secStopAt = e;" in done, "구간 끝에서 멈춰야 «이 구간»을 본 것"
    assert "p.play();" in done


def test_the_band_survives_a_video_the_browser_cannot_play():
    """일부 폰 영상은 브라우저가 재생만 못 한다 — 그래도 띠는 돌아야 한다."""
    body = JS.split("function secDur(){")[1].split("\n}")[0]
    assert "window._secFullDur" in body, "서버가 잰 길이로 되돌아가야 한다"
    assert "window._secFullDur = d.duration_s || 0;" in JS


@pytest.mark.parametrize("fn", ["applySecMode", "loadFullVideo", "suggestSecRanges",
                                "fillSectionsForm"])
def test_every_path_that_changes_the_times_repaints_the_band(fn):
    """🪄 자동으로 나누기·임시저장 복원 뒤 띠가 옛날 자리면 거짓말이 된다."""
    body = JS.split("function " + fn + "(")[1].split("\nfunction ")[0]
    assert "secBandsPaint()" in body, fn


def test_the_handles_do_not_collapse_onto_each_other():
    """시작=끝이면 길이 0짜리 구간이 생겨 렌더가 이상해진다."""
    body = JS.split("function bandDrag(")[1].split("\n}")[0]
    # 숫자 칸이 «초» 단위라 0.3초로는 반올림하면 같은 초가 된다 — 1초여야 한다
    assert "const MIN = 1;" in body
    assert "if(e < s + MIN) e = Math.min(g.dur, s + MIN);" in body
    assert "if(e < s + MIN) s = Math.max(0, e - MIN);" in body


def test_a_shaky_hand_still_grabs_a_handle():
    """손잡이를 정확히 못 눌러도 «가까운 쪽»이 잡혀야 한다 (어르신 회원)."""
    body = JS.split("function bandMake(")[1].split("\nfunction ")[0]
    assert "Math.abs(t - s0) <= Math.abs(t - e0) ? 's' : 'e'" in body
    assert "setPointerCapture" in body, "끌다 밖으로 나가도 계속 잡혀야"
    assert "pointercancel" in body


def test_the_edit_mode_trim_gets_the_same_band():
    """「✂️ 내 영상 편집」의 앞뒤 트림에도 같은 띠를 재사용한다."""
    assert 'id="trimBandBox"' in HTML
    body = JS.split("function initTrimBand(){")[1].split("\nfunction ")[0]
    assert "bandMake({" in body
    assert "window._trimStart = Math.round(Math.max(0, s) * 1e6);" in body
    assert "applyTrimMarks();" in body, "잘려 나가는 자막 줄이 눈에 보여야 한다"
    # 자막 검토 화면이 열릴 때 «반드시» 달려야 한다 — 안 그러면 영영 안 보인다
    boot = JS.split("resetSubPosBar(((window._settings||{}).subtitle||{}).margin_v);")[1]
    assert "initTrimBand();" in boot[:200]


def test_dragging_to_the_very_end_means_end_not_a_number():
    """기존 코드에서 _trimEnd 0 = «끝까지» — 끝에 붙였는데 숫자가 박히면 안 된다."""
    body = JS.split("function initTrimBand(){")[1].split("\nfunction ")[0]
    assert "window._trimEnd = (dur && e < dur - 0.05) ? Math.round(e * 1e6) : 0;" in body


def test_the_old_trim_buttons_are_untouched():
    """버튼을 없애면 «정확히 그 프레임»을 잡던 방법이 사라진다."""
    assert 'onclick="setTrimStart(event)"' in HTML
    assert 'onclick="setTrimEnd(event)"' in HTML
    assert "bandPaint(window._trimBand);" in JS.split("function updateTrimInfo(){")[1]


def test_the_server_contract_did_not_change():
    """띠는 «화면»에서만 바뀐 것 — 서버는 예전 그대로 초 단위를 받는다."""
    body = JS.split("async function startSections(){")[1].split("\nasync function ")[0]
    assert "start_us: s != null ? Math.round(s * 1e6) : null," in body
    assert "parseMMSS(((d.querySelector('.sec-start')||{}).value || ''))" in body
    assert '"start_us"' in SRC or "start_us" in SRC


def test_the_band_says_what_to_do_when_there_is_no_video_yet():
    """빈 띠가 아무 말도 없으면 «고장 났나» 싶다."""
    body = JS.split("function bandPaint(")[1].split("\nfunction ")[0]
    assert "band.classList.add('rb-off');" in body
    assert "lab.textContent = band.dataset.empty;" in body
    assert "끌어서 이 구간의 시작·끝을 정하세요" in JS
    assert "영상을 먼저 고르면" in JS
    assert "영상이 준비되면 여기를 끌어" in JS


# ══ 75: 자막이 말 한가운데서 끊기던 것 ═══════════════════════════
def test_the_members_own_example():
    """🔴 회원님이 적어 주신 바로 그 문장."""
    t = "안녕하세요 더브라운호텔입니다 여기가 좋은점은 뭐뭐 입니다"
    assert sg.split_ko_clauses(t) == [
        "안녕하세요", "더브라운호텔입니다", "여기가 좋은점은 뭐뭐 입니다"]
    assert sg.pack_ko_lines(t, 16) == [
        "안녕하세요 더브라운호텔입니다", "여기가 좋은점은 뭐뭐 입니다"]


@pytest.mark.parametrize("text,limit,want", [
    # 마침표가 하나도 없는 대본 — 예전엔 글자 수로만 잘렸다
    ("반갑습니다 오늘은 서울 강남 맛집을 소개할게요", 20,
     ["반갑습니다", "오늘은 서울 강남 맛집을 소개할게요"]),
    # 물음표·느낌표는 원래도 경계였다 — 깨지지 않았는지
    ("이거 아세요? 진짜 놀랐어요!", 12, ["이거 아세요?", "진짜 놀랐어요!"]),
    # 종결어미가 아예 없으면 예전처럼 단어 경계로
    ("가나다 라마바 사아자 차카타 파하", 8, ["가나다 라마바", "사아자 차카타", "파하"]),
])
def test_lines_end_where_the_talking_ends(text, limit, want):
    assert sg.pack_ko_lines(text, limit) == want


@pytest.mark.parametrize("word,text", [
    ("노래가요", "오늘은 노래가요 무대를 소개합니다"),
    ("데요리", "이 데요리는 정말 맛있습니다"),
    ("죠스바", "그 죠스바를 아시나요"),
    ("한다발", "꽃 한다발을 샀어요"),
])
def test_it_does_not_cut_inside_an_ordinary_word(word, text):
    """«가요»·«데요»·«죠»·«한다»는 낱말 속에도 산다 — 거기서 자르면 더 나쁘다."""
    clauses = sg.split_ko_clauses(text)
    assert any(word in c for c in clauses), f"{word}가 쪼개졌다: {clauses}"


def test_it_never_merges_across_a_full_stop():
    """🔴 처음 고칠 때 놓친 것 — 마침표는 «회원님이 직접 찍은» 경계다.

    말 단위로 나눈 뒤 다시 묶다 보니 마침표까지 넘어 묶었다. 그러면
    v1.14에서 고쳐 둔 «문장부호 우선 분할»(리포트 18번)이 도로 무너진다.
    전체 시험의 test_v114가 이걸 잡아 줬다.
    """
    t = "직원 여섯 명을 채용했습니다. 월급은 0원입니다. 농담 같죠? 화면 보세요."
    assert sg.pack_ko_lines(t, 32) == [
        "직원 여섯 명을 채용했습니다.", "월급은 0원입니다.", "농담 같죠?", "화면 보세요."]
    # 한도가 아무리 커도 마찬가지 — 길이가 아니라 «경계»의 문제다
    assert len(sg.pack_ko_lines(t, 200)) == 4


def test_a_clause_longer_than_the_limit_is_still_cut():
    """절 하나가 한도를 넘으면 어쩔 수 없이 자른다 — 무한정 길면 화면을 덮는다."""
    t = "오늘 소개할 곳은 서울 강남역 근처에 있는 아주 조용하고 깨끗한 호텔입니다"
    out = sg.pack_ko_lines(t, 14)
    assert len(out) >= 3
    assert all(len(x) <= 14 for x in out), out


def test_short_text_is_left_alone():
    assert sg.pack_ko_lines("안녕하세요", 20) == ["안녕하세요"]
    assert sg.pack_ko_lines("", 20) == []


@pytest.mark.parametrize("limit", [0, -1])
def test_no_limit_means_no_splitting(limit):
    assert sg.pack_ko_lines("안녕하세요 반갑습니다", limit) == ["안녕하세요 반갑습니다"]


def test_both_paths_use_the_same_rule():
    """대본으로 만든 영상과 «내 영상 편집»의 자막이 서로 다르게 끊기면 안 된다."""
    gen = open(sg.__file__, encoding="utf-8").read()
    assert "chunks = pack_ko_lines(text, limit)" in gen
    from cutdaejang.core import edit_mode
    ed = open(edit_mode.__file__, encoding="utf-8").read()
    assert "from .script_generator import pack_ko_lines" in ed
    assert "chunks = pack_ko_lines(text, limit)" in ed


def test_splitting_keeps_the_timing_proportional():
    """나눈 줄이 소리와 어긋나면 고친 게 아니라 망가뜨린 것이다."""
    from cutdaejang.core.edit_mode import Subtitle, split_long_subtitles
    subs = [Subtitle(
        text="안녕하세요 오늘은 서울 강남에 있는 더브라운호텔을 소개합니다 조식이 정말 좋아요",
        start_us=0, end_us=8_000_000)]
    out = split_long_subtitles(subs, wrap_chars=16, max_lines=2)   # 기본값 = 한도 32자
    assert [s.text for s in out] == [
        "안녕하세요", "오늘은 서울 강남에 있는 더브라운호텔을 소개합니다", "조식이 정말 좋아요"], \
        "예전엔 '오늘은 서울 강남에' / '있는 더브라운호텔을 소개합니다'로 말 한가운데서 끊겼다"
    assert out[0].start_us == 0
    assert out[-1].end_us == 8_000_000
    for a, b in zip(out, out[1:]):
        assert a.end_us == b.start_us, "틈이 생기면 자막이 깜빡인다"
        assert a.end_us > a.start_us


def test_split_long_sentences_keeps_the_script_usable():
    """문장을 나눴는데 강조·장면이 엉뚱한 곳으로 가면 영상이 이상해진다."""
    s = sg.Script(
        title="테스트",
        sentences=["안녕하세요 오늘은 서울 강남에 있는 더브라운호텔을 소개합니다 조식이 정말 좋아요"],
        highlights=["조식"],
        scene_prompts=["hotel lobby"],
    )
    out = sg.split_long_sentences(s, limit=20)
    assert len(out.sentences) > 1
    assert len(out.highlights) == len(out.sentences)
    assert len(out.scene_prompts) == len(out.sentences)
    assert out.scene_prompts[0] == "hotel lobby"
    hit = [h for h in out.highlights if h]
    assert hit == ["조식"], f"강조는 그 단어가 든 조각에만 — {out.highlights}"


def test_the_ai_is_told_the_same_rule():
    """코드로 나누는 건 «뒷수습»이다 — 애초에 AI가 그렇게 써 주는 게 낫다."""
    assert "말이 끝나는 곳" in sg.POLISH_PROMPT
    assert "안녕하세요 더브라운호텔입니다" in sg.POLISH_PROMPT


# ══ 화면이 여전히 성한가 ═════════════════════════════════════════
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
