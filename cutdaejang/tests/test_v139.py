"""v1.39 — 목록 77~81. 회원님 37~39차: 쇼핑 상품 영상을 실제로 만들며 나온 것들.

**세 건 전부 진짜 결함이었다.**

77 «배경음악을 랜덤으로 하니 어떤 건 소리가 들리고 어떤 건 안 들린다»
   랜덤이 문제가 아니라 **곡마다 원래 녹음된 크기가 다르기** 때문이었다.
   목소리는 받자마자 -16 LUFS로 맞추는데(tts_engine) BGM은 그런 게 없이
   «파일 크기 그대로»에서 몇 dB 낮추기만 했다. 원래 조용한 곡은 목소리와
   덕킹에 그대로 묻힌다.

78 자막이 «아직도» 말 한가운데서 끊긴다 (스크린샷의 자막 목록)
   v1.37이 고친 건 «부호 없는 대본을 종결어미로 나누는» 것이고,
   이건 «한 문장이 한도보다 길 때 어디서 자르나»다 — 그건 그냥 단어 경계였다.
   회원님 화면이 그대로 재현됐다.

79 「내 영상 편집」 상단 제목에서 색·크기·글씨체가 통째로 사라짐
   v1.35(목록 64)에서 «부모에 label이 있으면 그 줄을 통째로 옮긴다»고 했는데
   상단 제목 줄에 「비스듬히」 label이 있어 그 줄이 통째로 딸려 갔다.
   **내가 «정리»하면서 낸 버그다.**

80 «업로드 키트 설명문에 영어 크레딧이 들어가서 매번 지운다»
   → 설명문에서는 v1.36에 이미 뺐다(회원님 화면이 v1.35). 남은 별도 칸은
   CC BY의 «사용 조건»이라 지울 수 없다. 대신 «안 나오게» 하는 법을 적었다.

81 «폰 유튜브 앱은 최신 노래를 넣을 수 있는데 컷대장은 안 되냐»
   → 넣을 수 없다(권리 문제). 대신 그 결과를 얻는 길을 프로그램이 알려 준다.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui
from cutdaejang.utils import ffmpeg as ff

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.52.0"


# ══ 77: 배경음악이 곡마다 들쭉날쭉하던 것 ═══════════════════════
def _tone(dirpath, name, vol_db):
    p = Path(dirpath) / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anoisesrc=color=pink:duration=4:sample_rate=44100",
            "-af", f"volume={vol_db}dB", str(p)])
    return str(p)


def test_the_quiet_track_and_the_loud_track_end_up_the_same(tmp_path):
    """🔴 회원님이 겪은 것 — 원래 크기가 다른 곡이 그대로 다른 크기로 깔렸다."""
    loud = _tone(tmp_path, "loud.wav", 0)
    quiet = _tone(tmp_path, "quiet.wav", -10)
    li, qi = ff.measure_lufs(loud), ff.measure_lufs(quiet)
    assert li is not None and qi is not None
    assert li - qi > 8, "시험용 두 곡이 실제로 달라야 의미가 있다"

    before = abs((li - 16.0) - (qi - 16.0))          # 예전: 고정 dB만 뺐다
    lg, qg = ff.bgm_gain_db(loud, -16.0), ff.bgm_gain_db(quiet, -16.0)
    after = abs((li + lg) - (qi + qg))
    assert before > 8, before
    assert after < 1.0, f"맞춘 뒤에도 {after:.1f}dB 차이 — 여전히 들쭉날쭉하다"


def test_the_music_still_sits_under_the_voice(tmp_path):
    """맞춘다고 목소리만큼 키우면 그건 그것대로 못 쓴다 — 아래에 깔려야 한다."""
    p = _tone(tmp_path, "a.wav", 0)
    i = ff.measure_lufs(p)
    out = i + ff.bgm_gain_db(p, -16.0)
    assert -34 < out < -30, f"목소리(-16)보다 16dB 아래여야: {out:.1f}"


def test_a_file_we_cannot_measure_does_not_break_the_job(tmp_path):
    """재기 실패로 영상 만들기 전체가 멈추면 훨씬 나쁘다."""
    junk = tmp_path / "not_audio.mp3"
    junk.write_bytes(b"this is not audio at all")
    assert ff.measure_lufs(str(junk)) is None
    assert ff.bgm_gain_db(str(junk), -16.0) == -16.0        # 예전 그대로
    assert ff.bgm_gain_db(str(tmp_path / "없는파일.mp3"), -12.0) == -12.0


def test_a_deliberately_quiet_track_is_not_blasted(tmp_path):
    """앰비언스를 일부러 작게 만든 분도 있다 — 보정에 한도를 둔다."""
    tiny = _tone(tmp_path, "tiny.wav", -60)
    g = ff.bgm_gain_db(tiny, -16.0)
    assert g <= -16.0 + 20.0 + 0.01, f"보정 한도(20dB)를 넘었다: {g}"


def test_measuring_twice_only_runs_ffmpeg_once(tmp_path):
    """같은 곡을 여러 번 재면 만들기가 느려진다."""
    p = _tone(tmp_path, "c.wav", -3)
    ff.measure_lufs(p)
    calls = []
    real = subprocess.run

    def spy(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    subprocess.run = spy
    try:
        ff.measure_lufs(p)
    finally:
        subprocess.run = real
    assert not calls, "두 번째는 기억해 둔 값을 써야 한다"


@pytest.mark.parametrize("mod,what", [
    ("core/video_editor.py", "완성 영상에 BGM만 얹기"),
    ("core/edit_mode.py", "편집 렌더 · 소리만 갈아 끼우기"),
    ("core/render_engine/ffmpeg_composer.py", "대본으로 만드는 영상"),
])
def test_every_mixing_path_levels_the_music(mod, what):
    """한 군데라도 빠지면 그 경로만 예전처럼 들쭉날쭉해진다."""
    body = open(webui.__file__.replace("gui/webui.py", mod), encoding="utf-8").read()
    assert "bgm_gain_db(" in body, what


# ══ 78: 긴 문장을 «어디서» 자르나 ════════════════════════════════
MEMBER = [
    # (회원님 화면에 나온 문장, 예전에 잘리던 자리)
    ("특히 수많은 제품 중에서도 리뷰가 무려 2023개나 쌓인 게 있어.", "게 있어."),
    ("바로 약 60,200원에 올라와 있는 듀플렉스 에어 서큘레이터에요.", "서큘레이터에요."),
    ("심지어 실사용자 별점이 4.6점일 정도로 평이 엄청 좋거든요.", "좋거든요."),
]


@pytest.mark.parametrize("text,orphan", MEMBER)
def test_the_members_own_screen(text, orphan):
    """🔴 스크린샷 그대로 — 저 조각만 홀로 남는 줄이 생기면 안 된다."""
    out = sg.pack_ko_lines(text, 32)
    assert len(out) == 2, out
    assert out[-1] != orphan, f"예전 그대로 잘렸다: {out}"
    assert "".join(out).replace(" ", "") == text.replace(" ", ""), "글자가 사라졌다"


def test_a_word_is_never_cut_in_half():
    """«듀플렉스 에어 / 서큘레이터» — 한 낱말이 두 줄에 걸치면 제일 나쁘다."""
    out = sg.pack_ko_lines("바로 약 60,200원에 올라와 있는 듀플렉스 에어 서큘레이터에요.", 32)
    assert any("에어 서큘레이터에요." in ln for ln in out), out


@pytest.mark.parametrize("adv", ["엄청", "무려", "정말", "너무", "아주", "특히", "바로", "약"])
def test_no_line_ends_with_an_adverb(adv):
    """부사는 «다음 말»을 꾸민다 — 뒤에서 끊으면 문장이 붕 뜬다."""
    text = f"오늘 소개할 이 제품은 사용자 평가가 {adv} 좋다고 알려져 있습니다."
    for ln in sg.pack_ko_lines(text, 24):
        assert not ln.rstrip().endswith(adv), f"{adv} 뒤에서 끊겼다: {ln}"


def test_a_bound_noun_keeps_its_predicate():
    """«쌓인 게 / 있어» — 의존명사만 남기고 서술어를 떼면 말이 안 된다."""
    out = sg.pack_ko_lines("여기 리뷰가 무려 이천 개나 차곡차곡 쌓여 있는 제품이 하나 있어.", 20)
    for ln in out:
        assert ln.strip() not in ("게 있어.", "것 있어.", "수 있어.")


def test_it_does_not_leave_a_lonely_scrap():
    """한 줄이 다섯 자, 다음 줄이 서른 자면 보기에 나쁘다 — 고르게 나눈다."""
    out = sg.pack_ko_lines("심지어 실사용자 별점이 4.6점일 정도로 평이 엄청 좋거든요.", 32)
    assert len(out) == 2
    short, long_ = sorted(len(x) for x in out)
    assert short >= long_ * 0.4, f"너무 치우쳤다: {out}"


@pytest.mark.parametrize("word,text", [
    ("실사용자", "심지어 실사용자 별점이 아주 높은 편이라 믿을 만하다고 합니다."),
    ("화면", "이 화면 오른쪽 위에 있는 작은 버튼을 누르면 바로 저장이 됩니다."),
    ("최고", "제가 써 본 것 중에 최고 성능이라고 자신 있게 말씀드릴 수 있어요."),
])
def test_one_letter_endings_do_not_fool_it(word, text):
    """🔴 v1.37의 «노래가요» 함정과 같은 종류 — 실사용«자»·화«면»·최«고».

    한 글자 어미(고·면·며·자·든·듯)를 규칙에 넣으면 낱말 끝을 어미로 읽는다.
    """
    for ln in sg.pack_ko_lines(text, 22):
        assert not ln.rstrip().endswith(word), f"{word}를 어미로 읽었다: {ln}"


def test_short_sentences_are_untouched():
    for t in ("안녕하세요.", "오늘 날씨가 좋네요.", ""):
        assert sg.pack_ko_lines(t, 32) == ([t] if t else [])


def test_nothing_is_lost_no_matter_the_limit():
    """어떤 한도에서도 글자가 사라지거나 늘면 안 된다."""
    t = "특히 수많은 제품 중에서도 리뷰가 무려 2023개나 쌓인 게 있어."
    for limit in range(6, 60):
        out = sg.pack_ko_lines(t, limit)
        assert "".join(out).replace(" ", "") == t.replace(" ", ""), (limit, out)
        assert all(len(x) <= limit for x in out), (limit, out)


def test_both_paths_still_share_the_rule():
    ed = open(webui.__file__.replace("gui/webui.py", "core/edit_mode.py"),
              encoding="utf-8").read()
    assert "chunks = pack_ko_lines(text, limit)" in ed


# ══ 79: 상단 제목에서 사라졌던 조작들 ═══════════════════════════
def test_the_title_box_still_holds_its_own_controls():
    """🔴 색 칩·색 지우기·크기·글씨체·비스듬히가 한 줄(#hookStudio)에 있다."""
    seg = HTML.split('id="hookStudio"')[1].split("</details>")[0]
    for must in ("hookColorChips", "clearHookMarkup", "hookSizeSel",
                 "editHookFontSel", "editHookTiltChk"):
        assert must in seg, must


def test_moving_one_control_does_not_take_the_whole_row():
    """v1.35의 «부모에 label이 있으면 부모째» 규칙이 그 줄을 통째로 삼켰다."""
    body = JS.split("function mountDeco(")[1].split("\nfunction ")[0]
    assert "querySelectorAll('select,input,textarea,button').length" in body
    assert "nCtrl === 1" in body, "조작이 하나뿐인 줄만 통째로 옮겨야 한다"
    assert "el.previousElementSibling" in body, "칸과 «바로 앞 이름표»만 데려간다"
    assert body.count("inner.appendChild(p);") == 1


def test_the_summary_says_what_is_really_inside():
    """접힘 안내가 «색·글씨 스타일»이라 해놓고 없으면 찾아 헤맨다."""
    seg = HTML.split("🪝 상단 제목 넣기")[1][:160]
    assert "글씨체" in seg
    assert "글씨 스타일" not in seg, "글씨 스타일은 「🎨 꾸미기」로 갔다"
    assert "「🎨 꾸미기」에 있어요" in HTML, "어디로 갔는지 알려줘야 한다"


# ══ 80: 크레딧을 «안 나오게» 하는 법 ════════════════════════════
def test_the_credit_is_still_out_of_the_description():
    """v1.36에서 뺀 것이 되살아나지 않았는지."""
    assert "(설명란에 그대로 붙여넣기 — BGM 크레딧 포함)" not in HTML
    assert 'kit["bgm_credit"] = credit' in SRC


def test_the_screen_says_how_to_never_see_it_again():
    seg = HTML.split('id="kitBgm"')[1][:600]
    assert "저작자 표시가 «필요 없는» 곡" in seg
    assert "resources/bgm" in seg
    assert "이 칸이 아예 안 나옵니다" in seg


def test_my_own_music_still_adds_nothing():
    assert webui._bgm_credit("내가만든음악.mp3") == ""
    assert webui._bgm_credit("") == ""
    assert webui._bgm_credit("random") == ""


# ══ 81: 폰 앱에서 최신 음악 붙이기 ══════════════════════════════
def test_it_only_shows_up_when_there_is_no_music():
    """음악을 넣은 영상에 이 안내가 뜨면 잡음이다."""
    body = JS.split("function renderKit(")[1]
    assert "kit.phone_music" in body
    assert "$('kitPhoneRow').classList.toggle('hidden', !pm);" in body
    api = SRC.split("credit = _bgm_credit(bgm_name)")[1][:900]
    assert "elif not bgm_name:" in api, "음악이 없을 때만"
    assert 'kit["phone_music"]' in api


def test_the_guidance_is_actually_usable():
    """«유튜브 앱에서 하세요»만 적으면 초보자는 못 한다 — 순서가 있어야."""
    api = SRC.split('kit["phone_music"] = (')[1][:1400]
    for step in ("①", "②", "③", "④"):
        assert step in api, step
    for must in ("휴대폰", "사운드", "원본 소리"):
        assert must in api, must


def test_it_warns_why_burning_the_song_in_is_wrong():
    """이 안내의 «절반»은 하지 말아야 할 것이다 — 안 적으면 그냥 넣어 버린다."""
    api = SRC.split('kit["phone_music"] = (')[1][:1400]
    assert "Content ID" in api
    assert "1분 넘는 쇼츠는 아예 차단" in api
    assert "90초" in api, "쇼츠 3분 · 음악 90초 한도"


def test_the_text_file_carries_it_too():
    body = SRC.split("def _kit_text(")[1].split("\ndef ")[0]
    assert 'kit.get("phone_music")' in body
    assert "📱 폰에서 최신 음악 붙이기" in body


# ══ 화면이 여전히 성한가 ═══════════════════════════════════════
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
