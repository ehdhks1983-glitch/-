"""v1.25 — 상용화 판매 차단 (목록 39).

상용화 검토(docs/상용화_검토_v1.23.0.md)에서 "지금 팔면 안 되는 이유"로 꼽힌
7건을 코드·문서·빌드 세 층에서 막는다.

39-1 설치 bat의 FFmpeg 자동 다운로드가 100% 실패하던 cmd 지연확장 함정
39-2 내부 문서(오류 목록·경쟁분석·"사장님 전용" 배포 가이드)가 고객 zip에 포함
39-3 약관·환불·개인정보·AI 고지 등 판매 문서 0건
39-4 새 버전 알림 채널이 빈 채로 출고 (고쳐도 전달할 길이 없음)
39-5 「랜덤」 BGM을 쓰면 CC BY 저작자표시가 통째로 빠짐
39-6 인터넷 끊김(URLError)이 폴백 체인을 통째로 무산시킴
39-7 ✨AI 클립이 항상 가로 — 세로 쇼츠에서 유료 클립이 화면 1/3만 채움
"""

import urllib.error
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang.core import tts_engine as te
from cutdaejang.core.video_gen import clip_cache_path
from cutdaejang.gui import webui

ROOT = Path(__file__).resolve().parents[1]


def test_version():
    assert __version__ == "1.33.0"


# ── 39-1. 설치 bat: 블록 안 %VAR%가 빈 값이 되던 함정 ─────────────────
def test_installer_has_no_delayed_expansion_trap():
    """cmd는 괄호 블록을 통째로 파싱하며 %VAR%를 먼저 치환한다 —
    set이 실행되기 전이라 URL이 비어 다운로드가 언제나 실패했다."""
    bat = (ROOT / "windows/1_설치.bat").read_text(encoding="utf-8")
    assert "%FFURL%" not in bat                  # 변수 참조 자체를 없앴다
    assert "ffmpeg-master-latest-win64-gpl.zip" in bat   # 주소는 직접 박혀 있다
    assert bat.count("BtbN/FFmpeg-Builds") == 2          # curl + PowerShell 폴백


def test_all_bats_free_of_delayed_expansion_trap():
    """같은 함정이 다른 bat에 없는지 전수 검사 (블록 안 set → 같은 블록에서 사용)."""
    import re

    for bat in sorted(ROOT.glob("**/*.bat")):
        txt = bat.read_text(encoding="utf-8", errors="replace")
        if "enabledelayedexpansion" in txt.lower():
            continue                              # 지연확장을 켰으면 안전
        depth, cur = 0, None
        for i, ln in enumerate(txt.splitlines(), 1):
            s = ln.strip()
            if s.startswith("rem ") or s.startswith("::"):
                continue
            clean = s.replace("^(", "").replace("^)", "")
            opens, closes = clean.count("("), clean.count(")")
            if depth == 0 and opens > closes:
                cur = {"set": {}, "bad": []}
            if cur is not None:
                m = re.search(r'set\s+"?(\w+)=', s, re.I)
                if m:
                    cur["set"][m.group(1).upper()] = i
                for v in re.findall(r"%(\w+)%", s):
                    if v.upper() in cur["set"]:
                        cur["bad"].append((v, i))
            depth += opens - closes
            if depth <= 0 and cur is not None:
                assert not cur["bad"], f"{bat.name}: 블록 안 {cur['bad']}"
                cur, depth = None, max(0, depth)


def test_bgm_bat_uses_python_resolver():
    """「설치포함」 변형은 PATH에 파이썬이 없다 — 맨 python 호출이면 즉사한다."""
    bat = (ROOT / "windows/6_무료음원_받기.bat").read_text(encoding="utf-8")
    assert '"%PY%" -m cutdaejang.tools.fetch_bgm' in bat
    assert "find_python.bat" in bat


# ── 39-3. 판매 문서 ────────────────────────────────────────────────
SALES_DOCS = [
    "이용약관.txt", "환불·지원안내.txt", "개인정보_및_데이터_안내.txt",
    "AI_생성물_고지_안내.txt", "THIRD-PARTY-NOTICES.txt",
    "외부API_요금_주의.txt", "쇼핑수집_사용시_주의.txt", "무료음원_크레딧_사용법.txt",
]


@pytest.mark.parametrize("name", SALES_DOCS)
def test_sales_doc_exists_and_has_content(name):
    p = ROOT / "판매문서" / name
    assert p.is_file(), f"판매 문서 없음: {name}"
    assert len(p.read_text(encoding="utf-8").strip()) > 300


def test_sales_docs_cover_required_notices():
    """판매에 꼭 필요한 고지가 실제로 문장으로 들어 있는지."""
    doc = {n: (ROOT / "판매문서" / n).read_text(encoding="utf-8") for n in SALES_DOCS}
    assert "재배포" in doc["이용약관.txt"] and "환불" in doc["이용약관.txt"]
    assert "평문" in doc["개인정보_및_데이터_안내.txt"]        # 키 저장 방식 고지
    assert "%TEMP%" in doc["개인정보_및_데이터_안내.txt"]      # 브라우저 프로필 복사 고지
    assert "본인" in doc["AI_생성물_고지_안내.txt"]            # 목소리 클로닝 동의
    assert "후불" in doc["외부API_요금_주의.txt"]              # Veo 후불 과금 경고
    assert "비우지 마세요" in doc["외부API_요금_주의.txt"]      # 단가 0 = 한도 무력화
    assert "OFL" in doc["THIRD-PARTY-NOTICES.txt"]
    assert "GPL" in doc["THIRD-PARTY-NOTICES.txt"]
    assert "CC BY" in doc["무료음원_크레딧_사용법.txt"]


def test_user_guide_has_no_developer_repo():
    """고객이 받는 안내서에 내부 저장소 주소가 남으면 소스가 그대로 노출된다."""
    g = (ROOT / "실행가이드.md").read_text(encoding="utf-8")
    assert "git clone" not in g and "ehdhks1983" not in g
    assert "판매문서" in g          # 대신 판매 문서를 안내한다


# ── 39-2 / 39-4. 배포 위생 ─────────────────────────────────────────
def test_update_bat_ships_customer_docs_only():
    bat = (ROOT / "업데이트.bat").read_text(encoding="utf-8")
    assert "카페가이드.txt" in bat        # 고객용만 복사
    assert "판매문서" in bat              # 판매 문서도 함께 갱신
    assert 'xcopy "!SRC!\\docs" ".\\docs" /E' not in bat   # docs 통째 복사 금지


def test_update_channel_file_explains_requirement():
    t = (ROOT / "cutdaejang/update_url.txt").read_text(encoding="utf-8")
    assert "판매 전 반드시" in t and "version.json" in t


# ── 39-5. 랜덤 BGM도 크레딧이 나온다 ────────────────────────────────
def test_random_bgm_is_pinned_before_job_starts(tmp_path, monkeypatch):
    """시작 시점에 실제 곡으로 확정해야 크레딧(CC BY 저작자표시)이 만들어진다."""
    from cutdaejang.core import orchestrator

    (tmp_path / "코믹_Test Song.mp3").write_bytes(b"x" * 200)
    monkeypatch.setattr(orchestrator, "DEFAULT_BGM_DIR", tmp_path)
    params = {"bgm": "random"}
    webui._resolve_random_bgm(params)
    assert params["bgm"] == "코믹_Test Song.mp3"
    assert webui._bgm_credit(params["bgm"])          # 크레딧 문구가 나온다
    assert webui._bgm_credit("random") == ""         # 확정 전이면 여전히 빈 문구


def test_resolve_random_bgm_leaves_explicit_choice(tmp_path, monkeypatch):
    from cutdaejang.core import orchestrator

    monkeypatch.setattr(orchestrator, "DEFAULT_BGM_DIR", tmp_path)
    p = {"bgm": "잔잔_Easy Lemon.mp3"}
    webui._resolve_random_bgm(p)
    assert p["bgm"] == "잔잔_Easy Lemon.mp3"
    p2 = {}
    webui._resolve_random_bgm(p2)                    # 키가 없어도 예외 없음
    assert p2 == {}


# ── 39-6. 인터넷 끊김이 폴백 체인을 무산시키지 않는다 ──────────────────
def test_network_error_becomes_retryable_tts_error(monkeypatch):
    """URLError·타임아웃이 어느 except에도 안 걸려 폴백이 통째로 죽던 문제."""
    def boom(*_a, **_k):
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(te.urllib.request, "urlopen", boom)
    with pytest.raises(te.TTSError) as e:
        te._http_post_json("http://example.invalid", {}, {})
    assert not isinstance(e.value, te.TTSNonRetryable)   # 재시도·폴백 대상이어야 함
    assert "인터넷" in str(e.value)                       # 한국어로 설명


def test_timeout_also_becomes_tts_error(monkeypatch):
    def slow(*_a, **_k):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(te.urllib.request, "urlopen", slow)
    with pytest.raises(te.TTSError):
        te._http_post_json("http://example.invalid", {}, {})


# ── 39-7. AI 클립 세로 비율 ────────────────────────────────────────
def test_ai_clip_follows_section_layout():
    html = webui._HTML
    assert "'shorts' ? '9:16'" in html
    assert "aspect: '16:9'," not in html      # 하드코딩이 사라졌다


def test_clip_cache_key_separates_aspect():
    """비율이 키에 없으면 세로로 고쳐도 옛 가로 클립이 재사용된다."""
    a = clip_cache_path("/tmp", "veo", "m", "밤의 도시", 5, "720p", "16:9")
    b = clip_cache_path("/tmp", "veo", "m", "밤의 도시", 5, "720p", "9:16")
    assert a != b
    same = clip_cache_path("/tmp", "veo", "m", "밤의 도시", 5, "720p", "9:16")
    assert b == same                          # 같은 조건은 계속 재사용(과금 0)
