"""v1.17 — 🔰 쉬운 모드 + 설정 화면 접근성 (회원님 요청 22번).

> "설정 누르면 젤 하단 화면에 나와. 개별 작업할 때도 체크해야 하는 게 많아.
>  기능은 유지하되 사용을 간편하게 할 방법이 없어? (초보자 할아버지도)"

  ① ⚙설정·📇제품·🔑API 카드는 열리는 순간 그 자리로 자동 스크롤
  ② 🔰 쉬운 모드 — 각 카드에 필수 입력과 [시작]만 남기고 전부 숨김.
     숨긴 입력도 값은 살아 있어 페이로드는 자세히 모드와 100% 동일(기능 유지).
  ③ 쉬운 모드의 ⚙설정은 「🔊 소리·목소리」 묶음만 표시(easy-keep).
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from cutdaejang import __version__
from cutdaejang.gui import webui


def test_version():
    assert __version__ == "1.43.0"


def test_easy_mode_css_and_toggle_wired():
    html = webui._HTML
    for tok in ('id="easyBtn"', "function toggleEasy", "function applyEasy",
                "function _markEasyRows", "EASY_HIDE_IDS",
                'id="easyBar"', "저장된 설정 그대로",
                "body.easy .easy-hide { display: none !important; }",
                "body.easy #settingsCard details:not(.easy-keep)"):
        assert tok in html, tok
    # 상태는 설정에 기억되고, 켜기/끄기 라벨이 바뀐다
    assert "easy_mode: on" in html and "🛠 자세히" in html
    assert "applyEasy(!!(((s || {}).ui || {}).easy_mode));" in html


def test_easy_hides_options_but_keeps_essentials():
    html = webui._HTML
    body = html.split("EASY_HIDE_IDS")[1][:900]
    # 숨기는 것: 템플릿·배속·화질·목소리·훅 등 옵션 컨트롤들
    for tok in ("'tplSel'", "'autoQualitySel'", "'voiceSel'", "'secHook'",
                "'shopQualitySel'", "'wlBgmSel'"):
        assert tok in body, tok
    # 필수 입력은 절대 숨기지 않는다
    for essential in ("'topic'", "'editVideo'", "'photoPath'", "'weblinkUrl'",
                      "'shopLinkInput'", "'secFullPath'"):
        assert essential not in body, essential
    # 구간의 「대본 통째로 붙여넣기」·설정의 「소리·목소리」는 쉬운 모드에도 보인다
    assert html.count('class="opt easy-keep"') >= 2


def test_settings_card_scrolls_on_open():
    """v1.35에서 뒤집혔다 (목록 70) — 이제 «움직이면 안 된다».

    v1.17에는 설정이 페이지 맨 아래에 있어 «눌러도 아무 일 없는 것 같다»는
    리포트(22번)를 scrollIntoView로 덮었다. 그런데 그게 만들다 말고 맨 아래로
    끌려가는 불편이 되어 돌아왔다. 이제 옆 서랍으로 열려 페이지는 그대로 있고,
    닫으면 보던 자리 그대로다. 그래서 이 시험도 «안 움직이는지»를 본다.
    """
    html = webui._HTML
    seg = html.split("function toggleSettings")[1][:420]
    assert "scrollIntoView" not in seg
    assert "openDrawer('settingsCard'" in seg
    # 📇 내 제품 · 🔑 API 연동도 같은 병이라 같이 서랍으로 (목록 70)
    seg2 = html.split("function toggleApiCard")[1][:420]
    assert "scrollIntoView" not in seg2 and "openDrawer('apiCard'" in seg2
    seg3 = html.split("function toggleProductCard")[1][:420]
    assert "scrollIntoView" not in seg3 and "openDrawer('productCard'" in seg3


@pytest.fixture()
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("v117-jobs")
    iso = tmp_path_factory.mktemp("iso117")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(workdir), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env


def test_quick_set_persists_easy_mode(server):
    """토글 → settings.ui.easy_mode 저장 → 다음 접속에도 유지."""
    from cutdaejang import config

    req = urllib.request.Request(
        server + "/api/quick_set",
        data=json.dumps({"patch": {"ui": {"easy_mode": True}}}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        assert json.loads(r.read()).get("ok")
    assert config.load_settings()["ui"]["easy_mode"] is True
    # 이상한 값은 400으로 거절되고 저장도 안 된다 (bool만 허용)
    req = urllib.request.Request(
        server + "/api/quick_set",
        data=json.dumps({"patch": {"ui": {"easy_mode": "yes"}}}).encode(),
        headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=20)
    assert e.value.code == 400
    assert config.load_settings()["ui"]["easy_mode"] is True
