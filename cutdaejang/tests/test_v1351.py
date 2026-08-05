"""v1.35.1 — 목록 71: 깨진 «선택» 부품 하나가 프로그램 전체를 못 쓰게 만든 것.

회원님 31차 (스크린샷 2장, v1.31.0 실행):

  ① C:\\...\\webui.py, line 5183, in _state
       "stt_available": _stt_available(),
     ...
     FileNotFoundError: Could not find module '...\\ctranslate2\\ctranslate2.dll'

  ② cutdaejang.spec.SpecError: style 값 오류: size=0, outline=0
     [!] 실패했습니다. (데모 실행도 실패)

**두 화면은 한 사슬이다.**

  1. faster-whisper는 설치됐는데 그 아래 ctranslate2의 DLL이 깨져
     `FileNotFoundError`(=OSError)가 났다.
  2. `_stt_available()`은 `except ImportError`만 잡고 있어 안 잡혔다.
  3. 그 함수는 `_state()` 안이라 화면이 5초마다 부르는 **/api/state가 통째로 500**.
     → 프로그램 전체가 «안 되는» 것처럼 보인다.
  4. 상태를 못 받으니 설정 화면이 **빈 칸**으로 남는다.
  5. 그 상태로 [설정 저장]을 누르면 자바스크립트 `+""`는 0이라
     **font_size=0이 settings.json에 박제**된다.
  6. 그 뒤로는 UI든 데모 배치든 전부 `SpecError: size=0`으로 실패한다.
     프로그램을 다시 켜도 파일에 남아 있으니 계속 실패한다.

그래서 세 겹으로 막는다: ①선택 부품 격리 ②0을 저장하지 않기 ③읽을 때 되돌리기.
"""

import re

import pytest

from cutdaejang import __version__, config
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.41.0"


# ── ① 깨진 선택 부품이 프로그램 전체를 죽이지 않는다 ──────────────
def test_a_broken_whisper_does_not_kill_the_program(monkeypatch):
    """🔴 여기가 뿌리 — ImportError만 잡아서 DLL 깨짐이 위로 터졌다."""
    import builtins

    real = builtins.__import__

    def boom(name, *a, **kw):
        if name == "faster_whisper":
            raise FileNotFoundError(
                "Could not find module 'ctranslate2.dll' (or one of its dependencies)")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", boom)
    got = webui._stt_available()          # 예전엔 여기서 그대로 터졌다
    assert got["whisper"] is False
    assert got["whisper_why"], "왜 못 쓰는지 말해 줘야 한다"
    assert "FileNotFoundError" in got["whisper_why"]


def test_a_missing_whisper_says_install_it(monkeypatch):
    """아예 «안 깔린 것»과 «깔렸는데 못 부르는 것»은 다른 안내가 나가야 한다."""
    import builtins

    real = builtins.__import__

    def gone(name, *a, **kw):
        if name == "faster_whisper":
            raise ImportError("No module named 'faster_whisper'")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", gone)
    why = webui._stt_available()["whisper_why"]
    assert "설치되어 있지 않" in why and "5_영상편집_음성인식설치" in why


def test_the_heartbeat_survives_a_broken_piece():
    """/api/state는 화면이 5초마다 부른다 — 조각 하나가 터져도 살아야 한다."""
    assert "def _safe(self, name, fn, fallback)" in SRC
    body = SRC.split("def _state_inner(self)")[1].split("\n    def ")[0]
    assert 'self._safe("stt", _stt_available' in body
    assert 'self._safe("fonts"' in body


def test_the_engine_reports_a_broken_dll_in_korean():
    body = open(webui.__file__.replace("gui/webui.py", "core/stt_engine.py"),
                encoding="utf-8").read()
    seg = body.split("def _get_model(self)")[1].split("\n    def ")[0]
    assert "except Exception" in seg
    assert "Visual C++" in seg, "무엇을 해야 하는지 알려줘야 한다"


def test_the_screen_says_why_whisper_is_missing():
    assert "window._whisperWhy" in JS
    assert "무료 Whisper는 지금 못 써요" in JS


# ── ② 빈 칸을 0으로 저장하지 않는다 ────────────────────────────
def test_empty_boxes_are_never_saved_as_zero():
    """🔴 자바스크립트에서 +"" 는 0 — 그게 파일에 박제됐다."""
    body = JS.split("async function saveSettings(){")[1].split("\n}")[0]
    for gone in ("+$('setFontSize').value", "+$('setOutline').value",
                 "+$('setMarginV').value", "+$('setBgmVol').value",
                 "+$('setGap').value", "+$('setWrapChars').value"):
        assert gone not in body, gone
    assert "numOr('setFontSize'" in body and "numOr('setBgmVol'" in body


def test_numor_falls_back_instead_of_writing_garbage():
    body = JS.split("function numOr(")[1].split("\n}")[0]
    assert "if(raw === '') return fallback;" in body
    assert "if(!isFinite(n) || n < lo || n > hi) return fallback;" in body


# ── ③ 이미 박제된 파일은 읽을 때 되돌린다 (회원님 PC 자가 복구) ──
@pytest.mark.parametrize("bad,key,why", [
    ({"subtitle": {"font_size": 0}}, "font_size", "회원님 화면의 그 값"),
    ({"subtitle": {"font_size": -5}}, "font_size", "음수"),
    ({"subtitle": {"font_size": "84"}}, "font_size", "글자로 저장된 숫자"),
    ({"subtitle": {"font_size": 9999}}, "font_size", "말도 안 되게 큰 값"),
    ({"subtitle": {"outline": -1}}, "outline", "음수 외곽선"),
    ({"bgm": {"volume_db": -999}}, "volume_db", "말도 안 되는 볼륨"),
])
def test_poisoned_settings_repair_themselves(bad, key, why):
    sect = next(iter(bad))
    fixed = config._sanitize(bad)
    assert fixed, why
    assert bad[sect][key] == config.DEFAULTS[sect][key]


@pytest.mark.parametrize("ok", [
    {"subtitle": {"outline": 0}},          # 외곽선 0 = «없음» — 정상이다
    {"subtitle": {"wrap_chars": 0}},       # 0 = 줄바꿈 끔 — 정상이다
    {"subtitle": {"font_size": 84}},
    {"bgm": {"volume_db": -16}},
])
def test_legitimate_values_are_left_alone(ok):
    """0이 «항상» 잘못된 건 아니다 — 외곽선 0·줄바꿈 0은 정상 설정이다."""
    before = {k: dict(v) for k, v in ok.items()}
    assert config._sanitize(ok) == []
    assert ok == before


def test_load_settings_repairs_a_poisoned_file(tmp_path):
    """회원님 PC에 이미 남아 있는 파일이 «아무것도 안 해도» 되살아나야 한다."""
    import json

    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"subtitle": {"font_size": 0, "outline": 0}}),
                 encoding="utf-8")
    s = config.load_settings(str(p))
    assert s["subtitle"]["font_size"] == config.DEFAULTS["subtitle"]["font_size"]
    assert s["subtitle"]["outline"] == 0        # 0은 정상값이라 그대로


def test_the_repaired_settings_actually_pass_spec_validation(tmp_path):
    """되돌린 값으로 실제 렌더 검증을 통과해야 «고쳐진» 것이다."""
    import json

    from cutdaejang import presets, spec

    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"subtitle": {"font_size": 0}}), encoding="utf-8")
    s = config.load_settings(str(p))
    st = spec.Style(font="Pretendard-ExtraBold", size=s["subtitle"]["font_size"],
                    outline=s["subtitle"]["outline"], position="bottom")
    sp = spec.TimelineSpec(canvas=presets.CANVAS_SHORTS, style=st,
                           duration_us=1_000_000, audio=[], subtitles=[],
                           background=spec.Background(type="color", color="#101318"))
    sp.validate()                                # 예전엔 SpecError로 터졌다
    assert st.size > 0
