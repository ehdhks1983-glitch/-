"""v1.38 — 목록 76: 자막 «글씨체·효과»를 많이 쓰는 것으로 다양화.

회원님 35차:
> "자막 화면 자막 글씨체 효과 이런 부분들 조사 좀 해서
>  많이 쓰는 걸로 다양화가 더 필요할 것 같은데"

조사(76번) 결과 두 가지가 빠져 있었다.
  ① **단어별 자막** — 2026년 쇼츠에서 제일 많이 쓰는 연출인데 없었다.
     우리 카라오케는 «색이 차오르는» 것이라 결이 다르다.
  ② **굵기를 고를 수가 없다** — Pretendard Bold/SemiBold는 «이름표만» 있고
     파일이 없었다. 인터뷰·정보형에는 ExtraBold가 너무 굵다.

🔴 그리고 만들면서 더 큰 것을 찾았다. **이름표가 틀리면 libass는 오류를 내지 않고
«다른 글씨»로 그린다.** 파일마다 name 표를 읽고 렌더한 픽셀로 확인해 2건을 잡았다:
  · `Pretendard-Bold` → "Pretendard Bold"라는 이름은 그 파일에 없다 (name1은 "Pretendard")
  · `NanumPenScript-Regular` → name1이 "Nanum Pen"이다 ("Nanum Pen Script" 아님)
    **v0.63부터 나눔손글씨 펜을 고른 분은 기본 글씨로 나오고 있었다.**

그래서 이 파일의 핵심 시험은 «별칭이 실제로 그 글씨를 부르는가»를
**받아서·렌더해서** 확인한다. 문자열 비교로는 절대 못 잡는 종류의 결함이다.
"""

import hashlib
import pathlib
import re
import struct

import pytest

from cutdaejang import __version__, presets
from cutdaejang.core.render_engine import DEFAULT_FONTS_DIR
from cutdaejang.core.render_engine.ass_writer import _word_body, _word_spans
from cutdaejang.gui import webui
from cutdaejang.spec import Style, Subtitle
from cutdaejang.tools import fetch_fonts

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.43.0"


# ══ ① ✨ 단어별 자막 ═════════════════════════════════════════════
def _style(**kw):
    base = dict(font="Pretendard-ExtraBold", size=64, outline=3,
                position="bottom", anim="word", wrap_chars=0)
    base.update(kw)
    return Style(**base)


WORDS = [[0, 600_000, "안녕하세요"], [600_000, 1_200_000, "오늘은"],
         [1_200_000, 1_800_000, "강남"], [1_800_000, 2_400_000, "호텔을"],
         [2_400_000, 3_000_000, "소개합니다"]]
TEXT = "안녕하세요 오늘은 강남 호텔을 소개합니다"


def test_each_word_appears_at_its_own_time():
    """받아쓴 자막은 «말한 시각» 그대로 나타나야 한다."""
    sub = Subtitle(text=TEXT, start_us=0, end_us=3_000_000, words=WORDS)
    body = _word_body(sub, _style())
    starts = [int(m) for m in re.findall(r"\\t\((\d+),\d+,\\alpha&H00&\)", body)]
    assert starts == [0, 600, 1200, 1800, 2400], starts


def test_a_script_video_still_gets_the_effect():
    """🤖 AI 내레이션은 받아쓴 게 아니라 단어 시각이 없다 — 그래도 돌아야 한다."""
    sub = Subtitle(text=TEXT, start_us=0, end_us=3_000_000)
    spans = _word_spans(sub, sub.text)
    assert len(spans) == 5
    assert spans[0][0] == 0
    assert [s[2] for s in spans] == TEXT.split()
    for a, b in zip(spans, spans[1:]):          # 시간이 뒤로만 가야 한다
        assert a[0] <= b[0]
    assert spans[-1][0] < 3000, "마지막 단어가 자막이 끝난 뒤에 나오면 안 보인다"


def test_longer_words_get_more_time():
    """글자수 비례라 «소개합니다»가 «강남»보다 오래 걸려야 자연스럽다."""
    sub = Subtitle(text=TEXT, start_us=0, end_us=3_000_000)
    d = {t: b - a for a, b, t in _word_spans(sub, sub.text)}
    assert d["소개합니다"] > d["강남"]


def test_the_line_does_not_jump_around():
    """🔴 자리를 나중에 잡으면 단어가 늘 때마다 자막이 좌우로 덜컹거린다.

    투명(alpha FF)이어도 «글자 폭»은 차지하므로 처음부터 자리가 잡혀 있다 —
    즉 단어 사이 띄어쓰기가 태그 안이 아니라 글자 쪽에 붙어 있어야 한다.
    """
    sub = Subtitle(text=TEXT, start_us=0, end_us=3_000_000, words=WORDS)
    body = _word_body(sub, _style())
    assert body.count("\\alpha&HFF&") == 5, "모든 단어가 «처음엔 투명»이어야"
    plain = re.sub(r"\{[^}]*\}", "", body)
    assert plain == TEXT, f"글자·띄어쓰기가 그대로 남아야 자리가 안 흔들린다: {plain!r}"


def test_the_spoken_word_is_the_one_lit_up():
    """말하는 단어만 강조색, 지나가면 기본색으로 — 그래야 어디를 읽는지 보인다."""
    sub = Subtitle(text=TEXT, start_us=0, end_us=3_000_000, words=WORDS)
    body = _word_body(sub, _style())
    offs = [int(m) for m in re.findall(r"\\t\((\d+),\d+,\\1c&H[0-9A-Fa-f]{6}&\)", body)]
    assert offs == [600, 1200, 1800, 2400, 3000], offs


def test_no_words_no_crash():
    """빈 자막·공백만 있는 자막에서 터지면 그 작업 전체가 실패한다."""
    for txt in ("", "   "):
        sub = Subtitle(text=txt, start_us=0, end_us=1_000_000)
        assert _word_body(sub, _style()) == ""


def test_manual_colour_markup_still_wins():
    """[노랑]글자[/]로 직접 칠한 것을 효과가 덮으면 «내가 고친 게 사라진다»."""
    from cutdaejang.core.render_engine.ass_writer import dialogue_text

    sub = Subtitle(text="이건 [노랑]중요[/]합니다", start_us=0, end_us=2_000_000)
    body = dialogue_text(sub, _style())
    assert "\\alpha&HFF&" not in body, "수동 색이 있으면 단어별 효과는 비켜야"


def test_it_actually_reveals_on_screen(tmp_path):
    """🎬 여기가 진짜 확인 — 프레임을 뽑아 «글자가 늘어나는지» 픽셀로 본다.

    ASS 문자열이 그럴듯해도 libass가 태그를 무시하면 아무 일도 안 일어난다.
    시간이 갈수록 흰 픽셀이 늘고, 끝에서는 «효과 없음»과 비슷해져야 한다.
    """
    import subprocess

    from cutdaejang import presets as pr
    from cutdaejang import spec as sp
    from cutdaejang.core.render_engine.ass_writer import write_ass
    from cutdaejang.utils import ffmpeg as ff

    sub = Subtitle(text=TEXT, start_us=0, end_us=3_000_000, words=WORDS)

    def build(anim):
        st = _style(anim=anim, wrap_chars=16)
        s = sp.TimelineSpec(canvas=pr.CANVAS_SHORTS, style=st, duration_us=3_000_000,
                            audio=[], subtitles=[sub],
                            background=sp.Background(type="color", color="#000000"))
        return write_ass(s, str(tmp_path / f"{anim}.ass"))

    def ink(ass, t):
        png = tmp_path / f"{ass[-8:]}{t}.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "color=c=black:s=1080x1920:d=4:r=30", "-ss", str(t), "-frames:v", "1",
                "-vf", f"subtitles=filename={ass}:fontsdir={DEFAULT_FONTS_DIR}", str(png)])
        r = subprocess.run([ff.ffmpeg_bin(), "-v", "error", "-i", str(png),
                            "-vf", "format=gray", "-f", "rawvideo", "-"],
                           capture_output=True, check=True)
        return sum(1 for b in r.stdout if b > 128)

    word, none = build("word"), build("none")
    seq = [ink(word, t) for t in (0.2, 1.4, 2.9)]
    assert seq[0] < seq[1] < seq[2], f"글자가 하나씩 늘어야 한다: {seq}"
    full = ink(none, 0.2)
    assert seq[0] < full * 0.5, f"처음엔 일부만 보여야: {seq[0]} vs 전체 {full}"
    assert seq[2] > full * 0.8, f"끝에는 거의 다 보여야: {seq[2]} vs 전체 {full}"


@pytest.mark.parametrize("where", ["webui", "orchestrator"])
def test_the_new_effect_is_allowed_end_to_end(where):
    """허용 목록에서 빠지면 «골랐는데 조용히 무시»된다 — 제일 억울한 실패다."""
    if where == "webui":
        assert '_ANIMS = ("none", "pop", "type", "karaoke", "word")' in SRC
        assert SRC.count('("none", "pop", "type", "karaoke")') == 0, "옛 목록이 남아 있다"
    else:
        body = open(
            webui.__file__.replace("gui/webui.py", "core/orchestrator.py"),
            encoding="utf-8").read()
        assert '"karaoke", "word"' in body


def test_no_hint_points_at_a_button_we_removed():
    """🔴 v1.38.1 — 회원님 36차 화면 보고에서 드러난 것.

    v1.36에서 첫 화면의 「✨ AI로 영상 만들기」 카드를 뺐는데(목록 72 ①),
    그 카드를 «가리키던» 안내 두 곳이 남아 있었다. 없는 버튼을 찾아 헤매게 된다.
    안내는 «지금 있는 곳»을 가리켜야 한다.
    """
    assert "첫 화면의 [✨ AI로 영상 만들기]" not in HTML
    titles = re.findall(r'<span class="mc-title">([^<]+)</span>', HTML)
    assert "AI로 영상 만들기" not in titles, "카드가 되살아났다"
    # fal.ai 키 안내가 «실제로 있는» 버튼을 가리키는가
    for btn in ("[✨ AI 영상으로]", "[✨ AI 클립]"):
        assert btn in HTML, btn
    seg = HTML.split("✨ fal.ai (AI 영상 클립)")[1][:400]
    assert "만드는 화면마다" in seg


def test_the_screen_offers_it():
    assert '<option value="word">' in HTML
    assert "단어별" in HTML and "2026" in HTML


# ══ ② 🔤 글씨체 — 이름표가 «진짜» 그 글씨를 부르는가 ════════════
def _name_table(path: pathlib.Path) -> dict:
    """폰트 파일 안의 name 표에서 영문 이름들을 꺼낸다 (표준 라이브러리만)."""
    b = path.read_bytes()
    num = struct.unpack(">H", b[4:6])[0]
    tables = {}
    for i in range(num):
        s = 12 + i * 16
        tag, _, off, ln = struct.unpack(">4sIII", b[s:s + 16])
        tables[tag] = (off, ln)
    off, _ = tables[b"name"]
    _, cnt, so = struct.unpack(">HHH", b[off:off + 6])
    out = {}
    for i in range(cnt):
        s = off + 6 + i * 12
        pid, _eid, lid, nid, ln, no = struct.unpack(">HHHHHH", b[s:s + 12])
        if pid == 3 and lid == 0x409 and nid in (1, 4):
            out.setdefault(nid, b[off + so + no:off + so + no + ln]
                           .decode("utf-16-be", "ignore"))
    return out


def test_every_downloadable_font_has_a_family_alias():
    """별칭이 없으면 그 글씨체는 «고를 수는 있는데 안 나오는» 상태가 된다."""
    stems = [pathlib.Path(f).stem for f, _, _ in fetch_fonts.FONTS]
    missing = [s for s in stems if s not in presets.FONT_FAMILY_ALIASES]
    assert not missing, missing


def test_the_screen_offers_exactly_what_we_can_get():
    """화면 목록과 받기 목록이 어긋나면 «받기 필요»가 영원히 안 없어진다."""
    opts = set(re.findall(r'<option value="([^"]+)">', HTML))
    stems = {pathlib.Path(f).stem for f, _, _ in fetch_fonts.FONTS}
    assert stems <= opts, f"화면에 없는 글씨체: {sorted(stems - opts)}"
    assert HTML.count('<option value="NotoSansKR-Bold">') == 4, "글씨체 칸 4곳 모두에"


def test_the_bundled_font_name_matches_its_alias():
    """동봉 글씨체만이라도 «파일이 말하는 이름»과 별칭이 같아야 한다."""
    p = pathlib.Path(DEFAULT_FONTS_DIR) / "Pretendard-ExtraBold.ttf"
    if not p.is_file():
        pytest.skip("동봉 폰트 없음")
    n = _name_table(p)
    assert presets.FONT_FAMILY_ALIASES["Pretendard-ExtraBold"] in (n.get(1), n.get(4))


@pytest.mark.parametrize("stem,family", sorted(presets.FONT_FAMILY_ALIASES.items()))
def test_the_alias_is_a_name_the_file_actually_has(stem, family):
    """🔴 이 시험이 두 건을 잡았다 (Pretendard-Bold · NanumPenScript-Regular).

    별칭은 «지어낸 이름»이면 안 된다. 파일 안 name 표의 name1(패밀리) 또는
    name4(풀네임)와 같아야 libass가 찾는다. 아니면 조용히 다른 글씨로 그린다.
    (받아 둔 파일이 있을 때만 확인 — 없으면 건너뛴다)
    """
    fd = pathlib.Path(DEFAULT_FONTS_DIR)
    fp = next((fd / (stem + e) for e in (".ttf", ".otf") if (fd / (stem + e)).is_file()),
              None)
    if fp is None:
        pytest.skip(f"{stem} 안 받음")
    n = _name_table(fp)
    assert family in (n.get(1), n.get(4)), \
        f"{stem}: 별칭 {family!r} ≠ 파일의 이름 {n.get(1)!r}/{n.get(4)!r}"


def test_a_downloaded_font_is_not_silently_replaced(tmp_path):
    """🎬 렌더해서 확인 — 없는 이름을 쓰면 libass는 «기본 글씨»로 그린다.

    받아 둔 글씨체마다 같은 글자를 그려, ①기본 글씨와 다르고 ②서로도 다른지 본다.
    문자열 검사로는 절대 못 잡는 결함이다.
    """
    from cutdaejang.utils import ffmpeg as ff

    fd = pathlib.Path(DEFAULT_FONTS_DIR)
    have = {stem: fam for stem, fam in presets.FONT_FAMILY_ALIASES.items()
            if any((fd / (stem + e)).is_file() for e in (".ttf", ".otf"))}
    if not have:
        pytest.skip("받아 둔 글씨체가 없음")   # 새로 받은 PC에선 동봉 1종이라도 돈다

    tpl = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 300\n"
           "WrapStyle: 2\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, "
           "PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
           "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding\n"
           "Style: S,{f},80,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,"
           "5,20,20,20,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, "
           "MarginR, MarginV, Effect, Text\n"
           "Dialogue: 0,0:00:00.00,0:00:02.00,S,,0,0,0,,컷대장 가나다라 ABC 123\n")

    def shot(family):
        a = tmp_path / "t.ass"
        a.write_text(tpl.format(f=family), encoding="utf-8")
        p = tmp_path / "o.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "color=c=black:s=1080x300:d=0.1", "-frames:v", "1",
                "-vf", f"subtitles=filename={a}:fontsdir={fd}", str(p)])
        return hashlib.md5(p.read_bytes()).hexdigest()

    fallback = shot("ZZ이런이름의폰트는없다ZZ")
    seen = {}
    for stem, family in sorted(have.items()):
        h = shot(family)
        assert h != fallback, f"{stem}: 별칭 {family!r}로는 안 불린다 (기본 글씨로 그려짐)"
        assert h not in seen, f"{stem}와 {seen[h]}가 같은 글씨로 그려진다"
        seen[h] = stem


def test_the_program_itself_notices_a_wrong_name(tmp_path):
    """🔎 시험만으로는 부족하다 — 배포처가 나중에 이름을 바꾸면 회원님 PC에서만
    조용히 실패한다. 그래서 «받을 때» 프로그램이 직접 확인하게 했다."""
    real = pathlib.Path(DEFAULT_FONTS_DIR) / "Pretendard-ExtraBold.ttf"
    if not real.is_file():
        pytest.skip("동봉 폰트 없음")
    assert "Pretendard ExtraBold" in fetch_fonts.font_names(real)
    # 폰트가 아닌 파일을 줘도 터지지 않아야 한다 (받기 전체가 실패하면 안 된다)
    junk = tmp_path / "junk.ttf"
    junk.write_bytes(b"not a font at all")
    assert fetch_fonts.font_names(junk) == set()
    # 별칭이 틀리면 check_names가 집어낸다
    d = tmp_path / "f"
    d.mkdir()
    (d / "NanumPenScript-Regular.ttf").write_bytes(real.read_bytes())
    bad = [b[0] for b in fetch_fonts.check_names(str(d))]
    assert "NanumPenScript-Regular" in bad, "이름이 다른데 못 잡았다"


def test_the_screen_says_it_when_a_font_will_not_show_up():
    """받았다고만 하고 «안 나온다»는 걸 안 알려주면 원인을 영영 못 찾는다."""
    api = SRC.split('elif path == "/api/fetch_fonts":')[1].split("elif path ==")[0]
    assert '"mismatch": r.get("mismatch") or []' in api
    body = JS.split("async function fetchFonts(")[1].split("\n}")[0]
    assert "d.mismatch" in body
    assert "자막에 안 나올 수 있어요" in body


def test_the_preview_can_serve_an_otf():
    """새 글씨체 3종은 .otf다 — .ttf만 찾으면 화면 미리보기가 빈칸이 된다."""
    seg = SRC.split('elif path.startswith("/font/"):')[1].split("elif path.startswith")[0]
    assert 'for e in (".ttf", ".otf")' in seg
    assert "allowed" in seg, "화이트리스트(경로 주입 차단)는 그대로 있어야"


# ══ ③ 라이선스 — 넣어도 되는 것만 넣었는가 ═══════════════════════
def test_we_do_not_ship_a_font_we_may_not_redistribute():
    """이건 «파는» 프로그램이다 — 받아 주는 것도 배포에 가깝다."""
    src = open(fetch_fonts.__file__, encoding="utf-8").read()
    for banned in ("Hanna", "hanna", "한나"):
        assert not any(banned in u for _, _, u in fetch_fonts.FONTS), banned
    assert "배민 한나체는 넣지 않았다" in src, "왜 없는지 코드에 남겨야 다음에 또 안 넣는다"


def test_every_download_comes_from_the_publisher():
    """출처가 «아무 데나»면 라이선스도 파일도 보증이 안 된다."""
    ok = ("fonts.gstatic.com",                              # Google Fonts (OFL)
          "raw.githubusercontent.com/orioncactus/pretendard",   # Pretendard 공식 (OFL)
          "raw.githubusercontent.com/fonts-archive/S-CoreDream")  # 에스코어드림 (재배포 허용)
    for _, label, url in fetch_fonts.FONTS:
        assert url.startswith("https://"), label
        assert any(o in url for o in ok), f"{label}: 낯선 출처 {url}"


def test_the_licence_note_names_every_source():
    note = fetch_fonts._LICENSE_NOTE
    for must in ("Open Font License", "Pretendard", "Noto Sans KR",
                 "에스코어드림", "S-Core", "재판매", "한나"):
        assert must in note, must


def test_the_button_tells_the_real_size():
    """8MB라고 해놓고 19MB를 받으면 «멈춘 줄» 알고 창을 닫는다."""
    assert "약 19MB" in HTML
    assert "약 8MB" not in HTML


# ══ 화면이 여전히 성한가 ═════════════════════════════════════════
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
