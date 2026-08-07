"""v1.53 — 목록 108~112: 사진 드래그·꾸미기 랜덤·움직임 6종·서버 창 숨김·끊김 소음.

회원님 53차:
> "순서도 마우스로 끌어서 바꿀 수 있게" (108)
> "기본 자막 등등 고르는 게 몇 가지 있는데 이것도 랜덤 기능 추가" (109)
> "움직임 효과가 2개뿐인데 다양한 효과 추가" (110)
> "이런 서버가 꼭 열려야지만 사용을 할 수가 있는 거야? 화면에 안 보이면
>  좋겠는데" (111) + 검은 창의 ConnectionAbortedError 트레이스백 캡처 (112)
"""

import re
from pathlib import Path

from cutdaejang import __version__, config
from cutdaejang.core.render_engine.ass_writer import _motion_tags
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))
SRC = Path(webui.__file__).read_text(encoding="utf-8")
ROOT = Path(config.__file__).resolve().parents[1]


def test_version():
    assert __version__ == "1.53.0"


# ── 108. 사진 순서 드래그 ──────────────────────────────────────
def test_photo_drag_helper_exists():
    assert "function _wirePhotoDrag" in JS
    for tok in ("dragstart", "dragover", "drop", "el.draggable = true"):
        assert tok in JS, tok


def test_shop_grid_wired_with_drag():
    """쇼핑 사진 그리드가 드래그 배선을 쓰고, 두 배열을 같이 옮긴다."""
    seg = JS.split("_wirePhotoDrag(box, '.shop-photo-item'")[1][:300]
    assert "_shopPhotos" in seg and "_shopPrev" in seg and "splice" in seg


def test_drag_hint_in_counter():
    assert "끌어다 놓으면 순서가 바뀌어요" in JS


# ── 109. 꾸미기 랜덤 ───────────────────────────────────────────
def test_roll_deco_button_and_function():
    assert "🎲 랜덤 꾸미기" in JS and "function rollDeco" in JS


def test_roll_deco_rolls_all_pickers_and_fires_change():
    body = JS.split("function rollDeco")[1][:1600]
    for tok in ("ids.sub", "ids.hook", "ids.font", "ids.tone",
                "'.qd-anim'", "'.qd-motion'",
                "dispatchEvent(new Event('change'"):
        assert tok in body, tok
    assert "!== 'rand'" in body, "감성 테마의 rand 값은 제외"


def test_roll_deco_syncs_tone_cards():
    assert "function _syncToneCards" in JS
    assert "tonerow[data-for=" in JS


# ── 110. 움직임 효과 6종 ───────────────────────────────────────
def test_new_motions_render_t_chains():
    for m in ("float", "swing", "bounce", "shine"):
        t = _motion_tags(8000, m)
        assert t.startswith("{\\t(") and t.count("\\t(") > 5, m
        assert _motion_tags(900, m) == "", f"{m}: 짧으면 생략"


def test_motion_tag_contents():
    assert "\\fscx103" in _motion_tags(8000, "float")
    assert "\\frz3.2" in _motion_tags(8000, "swing")
    assert "\\fscy110" in _motion_tags(8000, "bounce")
    assert "\\blur2.4" in _motion_tags(8000, "shine")
    assert _motion_tags(8000, "pulse")            # 기존 2종 그대로
    assert _motion_tags(8000, "wiggle")


def test_motion_options_and_preview_wired():
    for v in ("float", "swing", "bounce", "shine"):
        assert f'value="{v}"' in HTML, v
    for k in ("pvFloat", "pvSwing", "pvBounce", "pvShine"):
        assert f"@keyframes {k}" in HTML, k
        assert k in JS.split("function _pvApplyAnim")[1][:2600], k + " 미리보기 매핑"


# ── 111. 서버 창 숨김 + 유령 방지 ──────────────────────────────
def test_serve_detaches_windowless_on_windows():
    """Windows에서 자신을 창 없는 프로세스로 재실행 — 첫 설치 화면은 그대로."""
    seg = SRC.split("def serve(")[1][:2200]
    assert "CUTDAEJANG_DETACHED" in seg
    assert "0x08000000" in seg, "CREATE_NO_WINDOW"
    assert "CUTDAEJANG_SHOW_CONSOLE" in seg, "진단용 탈출구"


def test_idle_watchdog_shuts_down_ghost_server():
    seg = SRC.split("def _idle_exit")[1][:900]
    assert "_ACTIVE_JOBS > 0" in seg, "렌더 중엔 안 끈다"
    assert "_BGM_TASK" in seg, "받기 작업 중에도 안 끈다"
    assert "httpd.shutdown()" in seg
    assert "> 90" in seg and "> 900" in seg


def test_state_poll_feeds_heartbeat():
    assert "_last_poll" in SRC.split('path == "/api/state"')[1][:300]


def test_launcher_bat_explains_auto_close():
    s = (ROOT / "windows" / "2_UI실행.bat").read_text(encoding="utf-8",
                                                      errors="replace")
    assert "자동으로 닫히고" in s and "스스로 꺼져요" in s


# ── 112. 연결 끊김 소음 침묵 ───────────────────────────────────
def test_quiet_server_swallows_client_disconnects():
    srv = webui._QuietServer.__new__(webui._QuietServer)
    try:
        raise ConnectionAbortedError("[WinError 10053] 클라이언트 중단")
    except ConnectionAbortedError:
        srv.handle_error(None, ("127.0.0.1", 1))     # 트레이스백 없이 조용히


def test_quiet_server_still_reports_real_errors(capsys):
    srv = webui._QuietServer.__new__(webui._QuietServer)
    try:
        raise ValueError("진짜 버그")
    except ValueError:
        srv.handle_error(None, ("127.0.0.1", 1))
    assert "ValueError" in capsys.readouterr().err, "진짜 오류는 그대로 보여야"


def test_serve_file_covers_connection_aborted():
    assert "except (ConnectionError, TimeoutError):" in SRC
    assert "_QuietServer((" in SRC, "서버 생성도 조용한 서버로"
