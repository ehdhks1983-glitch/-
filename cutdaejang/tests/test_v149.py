"""v1.49 — 목록 99: 정품 코드 + 7일 무료 체험 + EXE 설치.

회원님 49차:
> "배포 파일 자체는 EXE 설치 파일이어야 하잖아? 그래서 내가 먼저 테스트를…
>  추가로 넣어야 할 게, 기본은 7일 무료로 쓸 수 있게 해야 하고, 내가 날짜를
>  넣을 수 있는 코드를 넣어야 해."

정직한 한계: 제품이 순수 파이썬이라 HMAC 비밀 열쇠를 완벽히 숨길 수 없다
(난독화는 casual 추출만 막는다). 이 시험이 지키는 것은 «위조·만료·형식이
거절되는가»와 «체험/잠금 상태가 정확한가»다.
"""

import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from cutdaejang import __version__, config
from cutdaejang.core import license as lic
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
JS = "\n".join(__import__("re").findall(r"<script>(.*?)</script>", HTML, __import__("re").S))


def test_version():
    assert __version__ == "1.49.0"


# ── 코드 서명·검증 ─────────────────────────────────────────────
def test_valid_code_round_trips():
    code = lic.make_code("20991231", "AB12")
    assert code.startswith("CD-20991231-")
    v = lic.verify_code(code, date(2026, 1, 1))
    assert v["valid"] and v["expiry"] == "2099-12-31"


def test_forged_code_rejected():
    """서명 한 글자만 바꿔도 거절 — 비밀 열쇠 없이 못 만든다."""
    code = lic.make_code("20991231", "AB12")
    forged = code[:-1] + ("A" if code[-1] != "A" else "B")
    assert not lic.verify_code(forged, date(2026, 1, 1))["valid"]
    # 날짜만 미래로 늘려도(서명 안 맞음) 거절
    tamper = "CD-20991231-" + code.split("-")[2][:-4] + "0000"
    assert not lic.verify_code(tamper)["valid"]


def test_expired_code_rejected():
    code = lic.make_code("20250101", "SEED")
    assert not lic.verify_code(code, date(2026, 1, 1))["valid"]
    # 만료 당일까지는 유효
    assert lic.verify_code(lic.make_code("20260601", "SEED"),
                           date(2026, 6, 1))["valid"]


def test_malformed_code_rejected():
    for bad in ("", "아무거나", "CD-2026-XX", "CD-20261231-", "XX-20261231-ABCDEFGHIJKL"):
        assert not lic.verify_code(bad)["valid"]


def test_seed_makes_codes_unique():
    """같은 날짜라도 시드가 다르면 코드가 달라 재판매 추적이 된다."""
    a = lic.make_code("20991231", "AAAA")
    b = lic.make_code("20991231", "BBBB")
    assert a != b and lic.verify_code(a)["valid"] and lic.verify_code(b)["valid"]


# ── 7일 체험 상태 ──────────────────────────────────────────────
def _iso(tmp_path, monkeypatch, settings):
    import json
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CUTDAEJANG_SETTINGS", str(p))
    monkeypatch.setenv("APPDATA", str(tmp_path))       # shadow 격리
    monkeypatch.setattr(lic, "_shadow_path", lambda: tmp_path / ".fp")


def test_fresh_install_is_trial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch, {"license": {"first_run": date.today().isoformat()}})
    s = lic.status()
    assert not s["licensed"] and s["trial"] and s["days_left"] == lic.TRIAL_DAYS


def test_trial_expires_after_7_days(tmp_path, monkeypatch):
    old = (date.today() - timedelta(days=lic.TRIAL_DAYS + 1)).isoformat()
    _iso(tmp_path, monkeypatch, {"license": {"first_run": old}})
    s = lic.status()
    assert not s["licensed"] and not s["trial"] and s["days_left"] == 0


def test_valid_code_unlocks_regardless_of_trial(tmp_path, monkeypatch):
    old = (date.today() - timedelta(days=99)).isoformat()
    code = lic.make_code("20991231", "SEED")
    _iso(tmp_path, monkeypatch, {"license": {"first_run": old, "code": code}})
    s = lic.status()
    assert s["licensed"] and s["expiry"] == "2099-12-31"


def test_expired_code_falls_back_to_lock(tmp_path, monkeypatch):
    """만료된 코드 + 체험도 끝 → 잠금 (licensed 아님)."""
    code = lic.make_code("20250101", "SEED")
    old = (date.today() - timedelta(days=99)).isoformat()
    _iso(tmp_path, monkeypatch, {"license": {"first_run": old, "code": code}})
    assert not lic.status()["licensed"]


def test_clock_rollback_flagged(tmp_path, monkeypatch):
    """마지막 본 날보다 오늘이 과거면 체험을 소진으로 본다 (시계 되돌리기)."""
    future = (date.today() + timedelta(days=30)).isoformat()
    _iso(tmp_path, monkeypatch,
         {"license": {"first_run": date.today().isoformat(), "last_seen": future}})
    lic.mark_first_run()                                # last_seen(미래) > today → clock_back
    s = lic.status()
    assert s["days_left"] == 0, "시계 되돌림 → 체험 소진 처리"


def test_save_code_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch, {})
    r = lic.save_code(lic.make_code("20991231", "SEED"))
    assert r["ok"]
    assert lic.status()["licensed"]
    assert not lic.save_code("CD-20991231-WRONGSIGN000")["ok"]


def test_first_run_written_to_two_places(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch, {})
    lic.mark_first_run()
    assert config.load_settings().get("license", {}).get("first_run")
    assert (tmp_path / ".fp").is_file(), "홈 숨김 파일에도 이중 기록"


# ── 화면 게이트 ────────────────────────────────────────────────
def test_lock_and_trial_ui_present():
    for tok in ('id="lockOverlay"', 'id="trialBar"', 'id="licInput"',
                "무료 체험이 끝났어요", "function applyLicense", "function submitLicense",
                "/api/save_license"):
        assert tok in HTML, tok


def test_gate_reads_state_every_poll():
    assert "applyLicense(state.license)" in JS, "poll마다 반영 (등록 즉시 열림)"
    assert "document.body.classList.add('locked')" in JS


def test_keygen_is_not_in_product():
    """🔴 코드 생성기가 제품에 들어가면 누구나 코드를 찍는다 — 루트에만."""
    product = Path(config.__file__).resolve().parents[1]      # cutdaejang/ (제품)
    assert not (product / "make_license.py").exists()
    assert not list(product.rglob("make_license.py")), "제품 트리 어디에도 없어야"
    # 저장소 루트에는 있다 (판매자 도구)
    repo_root = product.parent
    if (repo_root / "make_license.py").exists():
        src = (repo_root / "make_license.py").read_text(encoding="utf-8")
        assert "판매자 전용" in src
