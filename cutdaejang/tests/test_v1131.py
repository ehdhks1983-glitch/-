"""v1.13.1 — 🛒 쇼핑 사진 수집(크롤링) 4차 수정: 로그인 감지·엔진 고정·진단 표시.

회원님 리포트: [🌐 내 크롬 열기]를 써도 "아직 로그인 안 됨" + 사진 0장 반복.
  ① 쿠키 DB를 본체만 복사해 저널/WAL에 있는 **방금 한 로그인**을 놓침 → 동반 복사
  ② 쿠키 위치를 Default/ 로 가정 → 프로필 하위 폴더를 가정 없이 전부 훑음
  ③ 로그인 창(A 브라우저)과 수집(B 브라우저)이 갈리면 쿠키 암호를 못 풂 → 엔진 기억
  ④ 실패 지점이 화면에 안 남음 → login_debug()를 상태줄·사진 0장 메시지에 표시
"""

import sqlite3

from cutdaejang import __version__
from cutdaejang.gui import webui
from cutdaejang.tools import product_page as pp


def test_version():
    assert __version__ == "1.15.0"


# ── ① WAL에만 있는 로그인도 보인다 ───────────────────────────────
def _cookie_db_with_wal(db_path, hosts):
    """스키마는 본체에, 행(로그인 쿠키)은 WAL에만 있는 DB — 로그인 직후 상태."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE cookies (host_key TEXT)")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.executemany("INSERT INTO cookies VALUES (?)", [(h,) for h in hosts])
    con.commit()
    return con                                  # 열어둔 채 = 브라우저가 켜져 있는 상태


def test_wal_cookies_detected_while_browser_open(tmp_path, monkeypatch):
    prof = tmp_path / "browser_profile"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    con = _cookie_db_with_wal(prof / "Default" / "Network" / "Cookies",
                              [".coupang.com", "www.naver.com", ".example.org"])
    try:
        wal = prof / "Default" / "Network" / "Cookies-wal"
        assert wal.is_file() and wal.stat().st_size > 0   # 행이 정말 WAL에 있다
        assert pp.logged_in_hosts() == ["네이버", "쿠팡"]
    finally:
        con.close()


def test_cookie_db_found_in_any_profile_dir(tmp_path, monkeypatch):
    """Default/ 가 아니라 Profile 1/ 에 만들어져도 찾는다."""
    prof = tmp_path / "browser_profile"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    con = _cookie_db_with_wal(prof / "Profile 1" / "Network" / "Cookies",
                              [".coupang.com"])
    con.close()
    assert pp.logged_in_hosts() == ["쿠팡"]


def test_login_debug_reports_stage(tmp_path, monkeypatch):
    prof = tmp_path / "browser_profile"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    d = pp.login_debug()                       # 프로필 자체가 없음 (버튼 안 누름)
    assert d["profile"] is False and d["hosts"] == [] and d["cookies"] == 0
    con = _cookie_db_with_wal(prof / "Default" / "Network" / "Cookies",
                              [".coupang.com", ".daum.net"])
    try:
        d = pp.login_debug()
        assert d["profile"] is True
        assert d["cookies"] == 2 and d["hosts"] == ["쿠팡"]
        assert "Cookies" in d["db"] and not d["error"]
    finally:
        con.close()


# ── ③ 로그인 창과 수집이 같은 브라우저를 쓴다 ────────────────────
def test_open_login_remembers_engine_and_orders_candidates(tmp_path, monkeypatch):
    edge = tmp_path / "msedge.exe"
    chrome = tmp_path / "chrome.exe"
    edge.write_bytes(b"x")
    chrome.write_bytes(b"x")
    prof = tmp_path / "prof"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    monkeypatch.setattr(pp, "_browser_candidates",
                        lambda: [str(edge), str(chrome)])
    calls = []

    class _P:  # noqa: D401 — Popen 흉내
        def __init__(self, args, **kw):
            calls.append(list(args))

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", _P)
    assert pp.open_login_browser("https://example.com/") == ""
    assert calls and calls[0][0] == str(edge)
    assert "--profile-directory=Default" in calls[0]   # 쿠키 위치를 Default로 고정
    assert pp._engine_file().read_text(encoding="utf-8") == str(edge)
    assert pp.login_browser_name() == "엣지"           # 안내 문구가 실제 창과 일치
    assert pp._ordered_candidates()[0] == str(edge)    # 수집도 같은 엔진 먼저
    # 로그인 창을 크롬으로 연 적이 있으면 크롬이 먼저
    pp._engine_file().write_text(str(chrome), encoding="utf-8")
    assert pp._ordered_candidates()[0] == str(chrome)
    assert pp.login_browser_name() == "크롬"


# ── ①② 수집용 복제 프로필 — 어디서 찾았든 Default로, WAL까지 ────
def test_collect_profile_maps_any_profile_to_default_with_wal(tmp_path, monkeypatch):
    from pathlib import Path

    prof = tmp_path / "browser_profile"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    con = _cookie_db_with_wal(prof / "Profile 1" / "Network" / "Cookies",
                              [".coupang.com"])
    con.close()
    (prof / "Local State").write_text("{}", encoding="utf-8")
    (prof / "Profile 1" / "Preferences").write_text("{}", encoding="utf-8")
    dst = Path(pp._collect_profile())
    assert dst.name == "cutdaejang_session"
    assert (dst / "Default" / "Network" / "Cookies").is_file()   # 헤드리스가 여는 위치
    assert (dst / "Local State").is_file()                       # 쿠키 암호 키
    assert (dst / "Default" / "Preferences").is_file()
    src_wal = prof / "Profile 1" / "Network" / "Cookies-wal"
    if src_wal.is_file():                       # WAL이 남아 있으면 복제본에도 함께
        assert (dst / "Default" / "Network" / "Cookies-wal").is_file()


def test_collect_profile_still_falls_back_without_cookies(tmp_path, monkeypatch):
    prof = tmp_path / "browser_profile"
    prof.mkdir(parents=True)                    # 폴더만 있고 쿠키 DB는 없음
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    assert "cutdaejang_headless" in pp._collect_profile()


# ── ④ 화면 진단 배선 ────────────────────────────────────────────
def test_webui_surfaces_login_debug():
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "login_debug()" in src               # /api/shop_login 이 진단을 내려보냄
    assert "login_browser_name()" in src        # 열린 창 이름(크롬/엣지)을 응답에
    html = webui._apply_links(webui._HTML)
    for tok in ("왼쪽 버튼을 눌러 로그인 창을 먼저 열어주세요",
                "로그인 기록이 아직 없어요",
                "[↻ 다시 확인]을 눌러주세요",
                "로그인을 끝까지 마쳤는지 확인해 주세요",
                "확인 오류: "):
        assert tok in html, tok
    # 사진 0장 메시지에 로그인 상태가 붙는다 (두 branch 모두)
    assert src.count("로그인: 없음") >= 2
    assert "logged_in_hosts())" in src
