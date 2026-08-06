"""v1.45 — 목록 88(🌏 다국어 병기) + 89(강조색 스위치) + 90(⬇ 받기 허브).

회원님 44~45차:
> "중국어 일본어 영어 정도까지는 같이 나오게 하는 설정 같은 거 사진처럼"
> "글씨색이나 이런 걸 다 기본으로 한 것 같은데 저렇게 색이 나오는데
>  오류가 아닌지 체크도"  (→ 오류 아님: AI가 문장마다 강조 단어를 고르는 설계.
>  다만 끌 수 있어야 한다 — 89)
> "음원이랑 글씨체 등등 다운받는 것들은 메인 화면 위쪽에 받는 곳이 보이도록"

병기의 함정 하나를 여기서 못 박는다: 한글 글씨체에는 일본어 가나·중국어
간체가 없다. 이름만 적으면 libass가 «조용히» 기본체로 떨어져 두부(□)가
된다(v1.38 함정) — 그래서 전용 글씨체가 «설치돼 있을 때만» 쓰고, 화면은
고르는 순간 받기를 권한다.
"""

import json
import re
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.core import translator
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.gui import webui
from cutdaejang.spec import Canvas, Style, Subtitle, TimelineSpec
from cutdaejang.tools import fetch_fonts as ff

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.47.2"


# ── 🌏 번역 (88) ────────────────────────────────────────────────
def _fake_post(reply_lines):
    calls = {}

    def fake(url, payload, key, timeout=0):
        calls["prompt"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [
            {"text": json.dumps({"lines": reply_lines}, ensure_ascii=False)}]}}]}

    return fake, calls


def test_translate_keeps_line_count_and_strips_markup(monkeypatch):
    fake, calls = _fake_post(["Hello", "", "셋째"])
    monkeypatch.setattr(sg, "_post_ai", fake)
    out = translator.translate_lines(["안녕 «꿀팁»", "둘째 줄", "셋째"], "en", api_key="k")
    assert len(out) == 3
    assert out[0] == "Hello"
    assert out[1] == "", "응답이 빈 줄이면 병기 생략"
    assert out[2] == "", "원문과 똑같은 «번역»은 병기 무의미 — 뺀다"
    assert "«" not in calls["prompt"], "강조 표식은 번역에 방해 — 빼고 보낸다"
    assert "3줄" in calls["prompt"] or "3" in calls["prompt"]


def test_translate_without_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(sg.ScriptError):
        translator.translate_lines(["한 줄"], "en")
    with pytest.raises(sg.ScriptError):
        translator.translate_lines(["한 줄"], "xx", api_key="k")   # 미지원 언어


def _iso_settings(tmp_path, monkeypatch, body):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CUTDAEJANG_SETTINGS", str(p))


def _spec(subs):
    return TimelineSpec(canvas=Canvas(1080, 1920, 30), hook="제목",
                        subtitles=subs, style=Style(), duration_us=10**6)


def test_finalize_attaches_translations(tmp_path, monkeypatch):
    _iso_settings(tmp_path, monkeypatch, {"subtitle": {"sub_lang": "en"}})
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    fake, _ = _fake_post(["First", "Second"])
    monkeypatch.setattr(sg, "_post_ai", fake)
    spec = _spec([Subtitle(text="첫 줄", start_us=0, end_us=10**6),
                  Subtitle(text="둘째 줄", start_us=10**6, end_us=2 * 10**6)])
    note = translator.finalize(spec)
    assert spec.subtitles[0].trans == "First"
    assert spec.subtitles[1].trans == "Second"
    assert spec.style.sub_lang == "en", "렌더가 병기 글씨체를 고르는 근거"
    assert "영어 병기" in note and "2줄" in note


def test_finalize_never_blocks_render(tmp_path, monkeypatch):
    """🔴 키가 없어도·번역이 죽어도 영상은 나와야 한다 — 병기만 빠진 채."""
    _iso_settings(tmp_path, monkeypatch, {"subtitle": {"sub_lang": "ja"}})
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    spec = _spec([Subtitle(text="한 줄", start_us=0, end_us=10**6)])
    note = translator.finalize(spec)          # 예외가 밖으로 안 샌다
    assert spec.subtitles[0].trans == ""
    assert "생략" in note


def test_finalize_off_by_default(tmp_path, monkeypatch):
    _iso_settings(tmp_path, monkeypatch, {})
    spec = _spec([Subtitle(text="한 줄", start_us=0, end_us=10**6)])
    assert translator.finalize(spec) == ""
    assert spec.subtitles[0].trans == ""


# ── 🎨 강조색 스위치 (89) ───────────────────────────────────────
def test_highlight_switch_clears_ai_picks_but_not_manual_markup(tmp_path, monkeypatch):
    _iso_settings(tmp_path, monkeypatch, {"subtitle": {"highlight_on": False}})
    spec = _spec([Subtitle(text="핵심 단어가 있는 문장", start_us=0, end_us=10**6,
                           highlight="핵심"),
                  Subtitle(text="«직접» 칠한 문장", start_us=10**6, end_us=2 * 10**6)])
    note = translator.finalize(spec)
    assert spec.subtitles[0].highlight == "", "AI가 고른 강조는 뺀다"
    assert "«직접»" in spec.subtitles[1].text, "«» 수동 마크업은 그대로"
    assert "강조색 자동 끔" in note


def test_highlight_stays_on_by_default(tmp_path, monkeypatch):
    _iso_settings(tmp_path, monkeypatch, {})
    spec = _spec([Subtitle(text="문장", start_us=0, end_us=10**6, highlight="문장")])
    translator.finalize(spec)
    assert spec.subtitles[0].highlight == "문장"


# ── 병기 렌더 (88 — ASS) ────────────────────────────────────────
def _render(subs, **style_kw):
    spec = TimelineSpec(canvas=Canvas(1080, 1920, 30), hook="제목", subtitles=subs,
                        style=Style(**style_kw), duration_us=3 * 10**6)
    p = tempfile.mktemp(suffix=".ass")
    aw.write_ass(spec, p)
    return open(p, encoding="utf-8").read()


def test_trans_line_renders_small_and_below():
    t = _render([Subtitle(text="안녕하세요", start_us=0, end_us=10**6,
                          trans="Hello there")])
    assert "Style: Trans," in t
    sd = int(re.search(r"Style: Default,[^,]+,(\d+)", t).group(1))
    st = int(re.search(r"Style: Trans,[^,]+,(\d+)", t).group(1))
    assert 0.4 < st / sd < 0.65, "본문의 절반쯤"
    md = int(re.search(r"Style: Default,.*,(\d+),1$", t, re.M).group(1))
    mt = int(re.search(r"Style: Trans,.*,(\d+),1$", t, re.M).group(1))
    assert mt < md, "margin이 작다 = 본문보다 «아래»"
    assert "Hello there" in t


def test_no_trans_no_extra_events():
    t = _render([Subtitle(text="병기 없음", start_us=0, end_us=10**6)])
    assert ",Trans,," not in t, "병기 없는 자막에 빈 이벤트를 만들지 않는다"


def test_trans_respects_fade():
    t = _render([Subtitle(text="안녕", start_us=0, end_us=10**6, trans="Hi")],
                fade=True)
    line = [l for l in t.splitlines() if ",Trans,," in l][0]
    assert "\\fad(100,60)" in line


def test_trans_font_used_only_when_installed(tmp_path):
    """🔴 두부(□) 함정 — 일·중 전용 글씨체는 «설치돼 있을 때만» 이름을 적는다."""
    from cutdaejang.core.render_engine import DEFAULT_FONTS_DIR

    dummy = Path(DEFAULT_FONTS_DIR) / "NotoSansJP.ttf"
    existed = dummy.is_file()
    assert aw._trans_font(Style(sub_lang="ja")) == aw._trans_font(Style()) or existed, \
        "미설치면 본문 글씨체 그대로"
    if not existed:
        dummy.parent.mkdir(parents=True, exist_ok=True)
        dummy.write_bytes(b"x")
        try:
            assert aw._trans_font(Style(sub_lang="ja")) == "Noto Sans JP"
            assert aw._trans_font(Style(sub_lang="zh")) != "Noto Sans SC", \
                "중국어 파일은 없으니 여전히 본문 글씨체"
        finally:
            dummy.unlink()
    assert aw._trans_font(Style(sub_lang="en")) == aw._trans_font(Style()), \
        "영어는 모든 글씨체에 라틴이 있다 — 본문 글씨체"


def test_lang_font_registry_sane(tmp_path):
    assert set(ff.LANG_FONTS) == {"ja", "zh"}
    for lang, (fname, fam, url) in ff.LANG_FONTS.items():
        assert url.startswith("https://fonts.gstatic.com/"), "구글 정적 배포만"
        assert fname.endswith(".ttf")
    # 크기 문턱 — 몇 KB짜리 깨진 파일을 «있다»고 치면 두부가 난다
    small = tmp_path / "NotoSansJP.ttf"
    small.write_bytes(b"x" * 10)
    assert not ff.lang_font_installed("ja", tmp_path)
    small.write_bytes(b"x" * 200_000)
    assert ff.lang_font_installed("ja", tmp_path)
    assert ff.lang_font_installed("en", tmp_path), "라틴은 항상 준비된 셈"


# ── 서버 배선 (88·89·90) ────────────────────────────────────────
@pytest.fixture()
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    iso = tmp_path_factory.mktemp("iso145")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(tmp_path_factory.mktemp("wd145")), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig
    if old is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_quick_set_accepts_lang_and_highlight(server):
    from cutdaejang import config

    st, d = _post(server, "/api/quick_set", {"patch": {"subtitle": {"sub_lang": "ja"}}})
    assert st == 200 and d.get("ok")
    assert config.load_settings()["subtitle"]["sub_lang"] == "ja"
    st, d = _post(server, "/api/quick_set",
                  {"patch": {"subtitle": {"highlight_on": False}}})
    assert st == 200
    assert config.load_settings()["subtitle"]["highlight_on"] is False
    # 이상한 언어는 통째로 거절 (병기 켜진 줄 알았는데 안 켜지는 사고 방지)
    st, _ = _post(server, "/api/quick_set", {"patch": {"subtitle": {"sub_lang": "xx"}}})
    assert st == 400


def test_fetch_lang_font_validates_lang(server):
    st, d = _post(server, "/api/fetch_lang_font", {"lang": "xx"})
    assert st == 400 and "error" in d


def test_state_reports_lang_font_readiness(server):
    with urllib.request.urlopen(server + "/api/state", timeout=20) as r:
        st = json.loads(r.read())
    assert set(st.get("lang_fonts", {}).keys()) == {"ja", "zh"}


# ── 화면 (88·89·90) ─────────────────────────────────────────────
def test_settings_offer_lang_and_highlight():
    sel = HTML.split('id="setSubLang"')[1].split("</select>")[0]
    for v in ('value="en"', 'value="ja"', 'value="zh"'):
        assert v in sel
    assert 'id="setHl"' in HTML
    # 불러오기·저장 양쪽에 배선 — 한쪽만 있으면 재부팅에서 증발한다
    assert "$('setSubLang').value = s.subtitle.sub_lang || '';" in JS
    assert "sub_lang: $('setSubLang').value," in JS
    assert "highlight_on: $('setHl').checked," in JS


def test_deco_clone_copies_options_from_settings():
    """분신 셀렉트는 설정 서랍 것을 복사한다 — 따로 적으면 언젠가 어긋난다."""
    seg = JS.split("function _decoEffectRow(")[1].split("\nfunction ")[0]
    assert "qd-lang" in seg
    assert "[...lsrc.options].forEach" in seg
    assert "'qd-hl', 'highlight_on', 'setHl'" in JS.replace('"', "'")
    # 설정에서 바꿔도 분신이 따라온다
    mark = JS.split("function markQuickDeco(")[1].split("\nfunction ")[0]
    assert ".qd-lang" in mark


def test_picking_ja_or_zh_warns_about_tofu():
    seg = JS.split("function maybeOfferLangFont(")[1].split("\nfunction ")[0]
    assert "□" in seg, "두부 글자 경고"
    assert "fetchLangFont" in seg


def test_preview_shows_a_translation_sample():
    seg = JS.split("function renderDecoPreview(")[1].split("\nfunction ")[0]
    for sample in ("字幕はこんな感じ", "字幕就是这样", "Subtitles look like this"):
        assert sample in seg
    assert "강조색 자동은 꺼짐" in seg, "89 스위치가 미리보기에도 보인다"


def test_home_has_a_visible_download_hub():
    """90 — «메인 화면 위쪽에 받는 곳이 보이도록»."""
    assert "⬇ 무료 자료 받기" in HTML
    assert 'id="dlCard"' in HTML
    seg = HTML.split('id="dlCard"')[1].split('id="apiCard"')[0]
    assert "글씨체 10종" in seg
    assert "무료 배경음악 14곡" in seg
    assert "번역 병기용 글씨체" in seg
    assert "fetchFonts(event)" in seg and "fetchBgm(event)" in seg
    assert "fetchLangFont('ja', event)" in seg and "fetchLangFont('zh', event)" in seg
    # 상태 표시 — «받아야 하는지»를 화면이 말해준다
    assert "function refreshDlCard(" in JS
    for sid in ("dlFontsState", "dlJaState", "dlZhState"):
        assert f'id="{sid}"' in HTML


def test_render_paths_call_finalize():
    em = open("cutdaejang/core/edit_mode.py", encoding="utf-8").read()
    re_init = open("cutdaejang/core/render_engine/__init__.py", encoding="utf-8").read()
    assert "translator.finalize(ass_spec)" in em
    assert "finalize(spec)" in re_init


# ── 화면이 여전히 성한가 ───────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label", "span"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
