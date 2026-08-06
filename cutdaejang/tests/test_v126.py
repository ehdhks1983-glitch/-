"""v1.26 — 네이버 클립 제목·태그 개선 (조회수 진단 1번).

회원님 20차(2026-08-02, 네이버클립·틱톡·인스타 분석 화면 3장):
"업로드 키트 제목 키워드 이런 게 문제일 것 같은데"

실제 화면에서 확인된 것:
· 네이버 제목이 "추석 로켓그로스 입고 8월 준비 필수" 처럼 **명사만 쌓인 검색어 덩어리**.
  같은 영상의 틱톡 캡션("추석 대목 판매, 8월부터 준비 안 하면 품절로 눈물 흘려요 😢")과
  비교하면 넘기지 않게 붙잡는 힘이 전혀 없다.
· 제목 뒤에 태그가 8개 이상 붙고, 그중 상당수가 **제목에 이미 있는 단어의 반복**
  ("추석 로켓그로스 입고" + #추석판매 #로켓그로스 #추석대목) — 검색 범위가 안 넓어진다.

⚠ 정직한 한계: 숏폼 조회수의 주된 결정 요인은 제목이 아니라 첫 1~2초 이탈률이다.
이 수정은 "검색으로 들어온 사람이 안 넘기게" 하는 것까지가 범위다.
"""

from pathlib import Path

from cutdaejang import __version__
from cutdaejang.gui.webui import tidy_naver_tags

ROOT = Path(__file__).resolve().parents[1]


def test_version():
    assert __version__ == "1.47.1"


# ── 프롬프트 규칙 ────────────────────────────────────────────────
def test_naver_title_rule_demands_predicate():
    """명사 나열을 금지하고 서술어로 끝나는 훅을 요구한다."""
    src = (ROOT / "cutdaejang/core/script_generator.py").read_text(encoding="utf-8")
    assert "명사만 늘어놓은 제목 금지" in src
    assert "추석 로켓그로스 입고 8월 준비 필수" in src      # 실제 나쁜 예를 못 박음
    assert "붙잡는 한마디" in src
    assert "검색형 제목 30자 이내 — 네이버에 검색할 법한 명사구를 맨 앞에." not in src


def test_naver_tag_rule_is_five_to_seven():
    src = (ROOT / "cutdaejang/core/script_generator.py").read_text(encoding="utf-8")
    assert "naver_clip.tags: **5~7개**" in src
    assert "10~12개" not in src                            # 옛 규칙 잔존 금지
    assert "제목에 이미 쓴 단어를 태그에 다시 쓰지 않는다" in src


# ── 코드 안전장치 (AI가 규칙을 어겨도 걸러진다) ──────────────────────
def test_drops_tags_already_in_title():
    """회원님 실제 사례 — 제목과 같은 말을 반복하던 태그를 뺀다."""
    title = "로켓그로스 추석 입고, 8월 넘기면 품절이에요"
    tags = ["추석판매", "로켓그로스", "쿠팡셀러", "재고관리", "입고규정",
            "물류비용", "추석대목", "8월준비", "로켓그로스입고", "쿠팡"]
    out = tidy_naver_tags(title, tags)
    assert "로켓그로스" not in out and "로켓그로스입고" not in out
    assert "쿠팡셀러" in out and "재고관리" in out          # 제목이 못 잡는 표현은 남는다
    flat_title = "".join(title.split()).lower()
    for t in out:
        assert "".join(t.split()).lower() not in flat_title


def test_caps_tag_count():
    out = tidy_naver_tags("짧은 제목", [f"태그{i}" for i in range(20)])
    assert len(out) == 7


def test_keeps_longer_of_overlapping_tags():
    """'부가세'와 '부가세신고'가 같이 있으면 좁은 쪽(긴 쪽)만 남긴다."""
    out = tidy_naver_tags("추석 대목 준비", ["부가세", "부가세신고", "세금", "홈택스"])
    assert "부가세신고" in out and "부가세" not in out


def test_never_empties_tags_completely():
    """전부 제목과 겹쳐도 최소 3개는 남긴다 — 태그 0개면 검색 유입이 끊긴다."""
    out = tidy_naver_tags("쿠팡 셀러 부가세 환급 매입세액 공제",
                          ["쿠팡", "셀러", "부가세", "환급", "매입세액"])
    assert len(out) >= 3


def test_handles_empty_and_none():
    assert tidy_naver_tags("", []) == []
    assert tidy_naver_tags("제목", None) == []
    assert tidy_naver_tags("제목", ["#해시붙은태그"]) == ["해시붙은태그"]   # ＃ 제거


def test_dedupes_case_insensitively():
    out = tidy_naver_tags("제목", ["Shorts", "shorts", "쿠팡"])
    assert len([t for t in out if t.lower() == "shorts"]) == 1


# ── 배선: 서버가 화면·텍스트 파일에 같은 결과를 준다 ─────────────────
def test_cleanup_is_wired_into_kit_response():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert 'tidy_naver_tags(_nc.get("title") or "", _nc["tags"])' in src
    assert "태그 5~7개 · 제목과 안 겹치게" in src            # 안내 문구도 갱신
    assert "(검색형 제목 + 태그 10~12개)" not in src
