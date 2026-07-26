"""v0.86 — 타이핑 자막 싱크·타닥 효과음 + 감성 테마 + 🛍 상품 정보 붙여넣기."""

import json
import re
import threading
import time
import types
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v086_ui_present_and_wired():
    html = webui._HTML
    for tok in ('id="genThemeSel"', 'id="wlThemeSel"', 'id="secThemeSel"',
                "function applyTheme", "인스타 감성", "유튜브 예능",
                'id="wlPasteBox"', 'id="wlPasteText"', "function pickWlPhotos",
                "function loadWeblinkPasted", "SHOP_HOST_RE", "sub_anim"):
        assert tok in html, tok


def _t_times(body):
    return [int(x) for x in re.findall(r"\\t\((\d+),", body)]


def test_typing_paced_to_subtitle_duration():
    from cutdaejang.core.render_engine.ass_writer import _typing_body

    # 4초 자막 10자 → 초당 5자 하한(말속도 근처)으로 마지막 글자 ≈1.8초
    ts = _t_times(_typing_body("가나다라마바사아자차", "&HFFFFFF&", dur_ms=4000))
    assert 1500 <= ts[-1] <= 3200, ts[-1]
    # 짧은 자막에 글자가 많으면 상한(28cps)으로 자막 안에 다 나옴
    ts2 = _t_times(_typing_body("가" * 30, "&HFFFFFF&", dur_ms=1500))
    assert ts2[-1] <= 1300, ts2[-1]
    # dur 미지정 → 기존 20cps 폴백 (하위 호환)
    ts3 = _t_times(_typing_body("가나다라", "&HFFFFFF&"))
    assert ts3[-1] == 150, ts3[-1]


def test_dialogue_text_uses_duration_for_typing():
    from cutdaejang.core.render_engine.ass_writer import dialogue_text

    style = types.SimpleNamespace(anim="type", primary_color="&HFFFFFF&",
                                  highlight_color="&H00D4FF&", fade=False,
                                  wrap_chars=0)
    sub = types.SimpleNamespace(text="타이핑 싱크 확인 문장", highlight="",
                                words=None, start_us=1_000_000, end_us=5_000_000)
    ts = _t_times(dialogue_text(sub, style))
    assert ts and 1400 <= ts[-1] <= 3300, ts   # 4초 표시 시간에 맞춰 타이핑
    # 같은 문장이라도 표시 시간이 짧으면 더 빨리 찍힘
    sub2 = types.SimpleNamespace(text="타이핑 싱크 확인 문장", highlight="",
                                 words=None, start_us=0, end_us=1_200_000)
    ts2 = _t_times(dialogue_text(sub2, style))
    assert ts2[-1] < ts[-1]


@requires_ffmpeg
def test_sfx_key_synth_and_events(tmp_path):
    from cutdaejang.core import sfx

    paths = sfx.ensure_sfx(tmp_path)
    assert "key" in paths
    from pathlib import Path
    assert Path(paths["key"]).stat().st_size > 1000
    # 타이핑 자막 스펙 → 문장 시작마다 '타닥' 이벤트
    spec = types.SimpleNamespace(
        hook="", style=types.SimpleNamespace(anim="type"),
        audio=[types.SimpleNamespace(start_us=0),
               types.SimpleNamespace(start_us=3_000_000)],
        subtitles=[types.SimpleNamespace(text="a", highlight=""),
                   types.SimpleNamespace(text="b", highlight="")])
    events = sfx.build_events(spec, paths, {"volume_db": -13})
    keys = [e for e in events if e.name == "key"]
    assert len(keys) == 2 and keys[1].start_us == 3_000_000
    # 타이핑이 아니면 타닥 없음
    spec.style.anim = "none"
    events2 = sfx.build_events(spec, paths, {"volume_db": -13})
    assert not [e for e in events2 if e.name == "key"]


def test_job_options_sub_anim_mapping():
    from cutdaejang import config

    settings = config.load_settings()
    opts = webui._job_options({"sub_anim": "type", "topic": "테스트"}, settings)
    assert opts.sub_anim == "type"
    opts2 = webui._job_options({"sub_anim": "이상한값", "topic": "테스트"}, settings)
    assert opts2.sub_anim == ""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v086")
    iso = tmp_path_factory.mktemp("iso86")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"

    httpd = webui.create_server(str(workdir), port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env
    os.environ.pop("GEMINI_API_KEY", None)


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def test_fetch_url_pasted_text_e2e(server):
    """🛍 상품 정보 붙여넣기 — 크롤링 없이 대본 생성 (키 없으면 원문 문장 폴백)."""
    pasted = ("여름 무선 선풍기 후기입니다. 바람 세기가 4단계라 책상에서 쓰기 좋아요. "
              "한 번 충전하면 최대 12시간 갑니다. 소음도 작아서 사무실에서도 부담이 없어요. "
              "접이식이라 캠핑 갈 때도 챙겨가기 좋습니다.")
    d = _post(server, "/api/fetch_url",
              {"pasted_text": pasted, "url": "https://www.coupang.com/vp/products/123"})
    assert d.get("ok"), d
    t0 = time.time()
    t = {}
    while time.time() - t0 < 60:
        with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
            t = json.loads(r.read()).get("weblink_fetch") or {}
        if not t.get("running"):
            break
        time.sleep(0.5)
    assert not t.get("error"), t
    res = t.get("result") or {}
    assert res.get("script_lines"), res
    assert res.get("images") == []                     # 사진은 직접 고르는 흐름
    assert res.get("source_url", "").startswith("https://www.coupang.com")
    assert any("붙여넣" in n for n in res.get("notes") or [])
    # 너무 짧은 붙여넣기는 친절한 오류
    d2 = _post(server, "/api/fetch_url", {"pasted_text": "짧음"})
    assert "error" in d2
