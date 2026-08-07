"""v1.50 — 목록 100~103: EXE 첫 테스트에서 나온 4건.

회원님 50차 (EXE 설치 후 스크린샷 4장):
> "저렇게 검은창이 계속 떠야 하는 거야?" (100)
> "고객 피씨 고유코드 번호가 있어야 하는 거 아니야? 기존 봇들처럼.
>  그리고 화면이 닫히지를 않아" (101)
> "일레븐랩스 키 기존에 잘 사용하던 건데 안 되는 이유" (102)
> "무료 배경음악 다운이 안 되는 문제" (103)
"""

import re
import warnings
from datetime import date
from pathlib import Path

from cutdaejang import __version__, config
from cutdaejang.core import license as lic
from cutdaejang.core import tts_engine
from cutdaejang.gui import webui
from cutdaejang.tools import fetch_bgm as fb

HTML = webui._apply_links(webui._HTML)
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))
ROOT = Path(config.__file__).resolve().parents[1]
SRC = Path(webui.__file__).read_text(encoding="utf-8")


def test_version():
    assert __version__ == "1.51.0"


# ── 100. 검은 서버 창 ──────────────────────────────────────────
def test_launcher_bat_self_minimizes():
    """검은 창을 없앨 수는 없다(서버·종료 스위치) — 대신 최소화로 연다."""
    s = (ROOT / "windows" / "2_UI실행.bat").read_text(encoding="utf-8",
                                                      errors="replace")
    assert "CUTDAEJANG_MINIMIZED" in s and "/min" in s
    assert "최소화" in s, "안내 문구도 같이"


def test_no_invalid_escape_in_any_source():
    """설치 첫 화면에 SyntaxWarning(invalid escape)이 뜨지 않게 — 전 파일."""
    bad = []
    for p in Path(config.__file__).parent.rglob("*.py"):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
            bad += [(p.name, x.lineno) for x in w
                    if "invalid escape" in str(x.message)]
    assert not bad, bad


def test_js_regexes_survived_escape_fix():
    """이스케이프 고치기가 JS 정규식을 깨지 않았는지 — 평가된 JS 기준."""
    assert ".split(/[,\\s]+/)" in JS
    assert ".replace(/\\s*\\(.*$/" in JS


# ── 101. PC 고유코드 정품 (기존 봇 방식) ───────────────────────
def test_machine_code_stable_and_pretty():
    a, b = lic.machine_code(), lic.machine_code()
    assert a == b and len(a) == 8, "재호출에도 같은 8자"
    assert re.fullmatch(r"[A-Z2-7]{4}-[A-Z2-7]{4}", lic.machine_code_pretty())


def test_pc_bound_code_only_works_on_that_pc():
    mc = lic.machine_code()
    code = lic.make_code_pc("20991231", "AB12", mc)
    assert code.startswith("CP-")
    assert lic.verify_code(code, date(2026, 1, 1))["valid"], "내 PC → 통과"
    other = lic.verify_code(code, date(2026, 1, 1), mc="ZZZZ9999")
    assert not other["valid"], "다른 PC → 거절"


def test_pc_rejection_tells_member_their_code():
    """거절 문구에 «내 고유코드»가 나와야 회원이 판매자에게 보낼 수 있다."""
    code = lic.make_code_pc("20991231", "AB12", "AAAA2222")
    r = lic.verify_code(code, date(2026, 1, 1), mc="BBBB3333")
    assert "고유코드" in r["reason"] and "BBBB-3333" in r["reason"]


def test_generic_cd_codes_still_work():
    """이미 발급한 CD- 공용 코드(하위호환)는 그대로 유효."""
    code = lic.make_code("20991231", "AB12")
    assert lic.verify_code(code, date(2026, 1, 1))["valid"]


def test_expired_pc_code_rejected():
    code = lic.make_code_pc("20200101", "AB12", lic.machine_code())
    r = lic.verify_code(code, date(2026, 1, 1))
    assert not r["valid"] and "까지였어요" in r["reason"]


def test_lock_ui_shows_machine_code_with_copy():
    for tok in ('id="licMc"', 'id="licMcBtn"', "내 PC 고유코드",
                "function copyMc", "판매자(카페)에게 알려주면"):
        assert tok in HTML, tok
    assert "machine_code_pretty" in SRC, "/api/state에 고유코드 동봉"


def test_trial_open_is_closable_but_expired_lock_is_not():
    """체험 중 [정품 등록]으로 연 창엔 ✕, 체험 만료 잠금엔 ✕ 없음 (101)."""
    assert 'id="licClose"' in HTML and "function closeLicense" in JS
    assert "c.classList.remove('hidden')" in JS, "체험 분기 → 닫기 보임"
    assert "c.classList.add('hidden')" in JS, "만료 분기 → 닫기 숨김"
    assert "!window._licManual" in JS, "수동으로 연 창은 poll이 안 닫는다"
    assert "document.body.classList.contains('locked')" in JS, "잠금이면 닫기 무시"


def test_lock_title_matches_situation():
    """체험 중인데 «무료 체험이 끝났어요»가 뜨던 혼동 — 제목을 상황별로."""
    assert 'id="licTitle"' in HTML
    assert "🔑 정품 코드 등록" in JS and "무료 체험이 끝났어요" in JS


def test_apply_license_ignores_transient_empty_state():
    """상태 응답이 순간 비어도 잠갔다 풀었다 하지 않는다."""
    assert "typeof lic.licensed === 'undefined'" in JS


# ── 102. 일레븐랩스 거절 사유 한국어 ───────────────────────────
def test_eleven_error_korean_mapping():
    f = tts_engine._eleven_http_ko
    assert "권한" in f(401, '{"detail":{"status":"missing_permissions"}}')
    assert "다시 복사" in f(401, '{"detail":{"status":"invalid_api_key"}}')
    assert "한도" in f(429, '{"detail":{"status":"quota_exceeded"}}')
    assert "실패 500" in f(500, "server oops")


# ── 103. 무료 BGM 실패 원인 표시 ───────────────────────────────
def test_fetch_records_http_reason(tmp_path, monkeypatch):
    import urllib.error

    def boom(req, timeout):
        raise urllib.error.HTTPError("https://x/y.mp3", 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert fb.fetch("https://x/y.mp3", tmp_path / "a.mp3") is False
    assert "403" in fb.LAST_ERROR


def test_fetch_flags_html_response(tmp_path, monkeypatch):
    class R:
        def read(self):
            return b"<html>not a song</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: R())
    assert fb.fetch("https://x/y.mp3", tmp_path / "a.mp3") is False
    assert "파일이 아님" in fb.LAST_ERROR


def test_browserlike_ua_and_referer():
    """봇 티 나는 UA가 차단 원인 1순위 — 브라우저형 + Referer로 (103)."""
    ua = fb._HEADERS["User-Agent"]
    assert "Chrome" in ua and "cutdaejang" not in ua
    assert fb._HEADERS["Referer"].startswith("https://incompetech.com")


def test_main_collects_fail_reasons(tmp_path):
    def fake(url, dest):
        fb.LAST_ERROR = "HTTP 403 (사이트가 요청을 거절)"
        return False

    ok, fail = fb.main(bgm_dir=tmp_path, fetch_fn=fake)
    assert not ok and fail
    assert all("403" in fb.FAIL_WHY[t] for t in fail)


def test_bgm_ui_message_carries_reason():
    """화면 문구에 원인이 실려야 캡처 한 장으로 진단된다."""
    assert "FAIL_WHY" in SRC
    assert "이 문구를 캡처해 보내주세요" in SRC
