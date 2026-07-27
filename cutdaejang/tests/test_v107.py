"""v1.07 — 🅰 텍스트 카드 장면(전 카테고리) + 📝 작업 임시 저장 (사용자 요청 2건).

스샷 요청 "타이핑 글자가 나오면서 효과도 넣고" → 숫자·펀치 문장 구간을 화면
전체 어둡게 + 큰 타이포 팝 오버레이(ASS)로. 오버레이라 길이·내레이션·이음새를
안 건드려 생성·편집·사진·구간·블로그·쇼핑 전부 같은 코드로 적용 ("전체적으로").
"""

import dataclasses
import json
import threading
import urllib.request

import pytest

from cutdaejang.core import text_cards as tc
from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.gui import webui
from tests.test_spec import make_valid_spec


def test_pick_card_indices_rules():
    texts = ["시작하는 문장입니다 오늘도 좋아요",   # 평범 — 제외
             "300만 넘는 영상 300개",              # 숫자+단위 → 카드
             "95% 가 답입니다",                    # % → 카드... 인접이라 스킵될 수 있음
             "그 다음 이야기입니다 계속 이어져요",
             "단 하나의 차이",                     # 짧은 펀치(점수1) — 단독으론 제외
             "댓글 1,000개 이상 확인",             # 숫자+개 → 카드
             ]
    picked = tc.pick_card_indices(texts)
    assert 1 in picked and 5 in picked
    assert 2 not in picked                        # 1번과 인접 — 답답함 방지 규칙
    assert 0 not in picked and 4 not in picked
    # [카드] 수동 표시는 무조건 + 표시는 제거
    manual = tc.pick_card_indices(["[카드]단 하나의 차이", "다른 문장입니다"])
    assert manual == [0]
    assert tc.strip_mark("[카드]단 하나의 차이") == "단 하나의 차이"
    # 최대 4장
    many = [f"숫자 {i}개 입니다" for i in range(10)]
    assert len(tc.pick_card_indices(many)) <= 4


def test_write_ass_renders_card_scene(tmp_path):
    spec = make_valid_spec()
    subs = list(spec.subtitles)
    subs[1] = dataclasses.replace(subs[1], text="300만 넘는 영상 300개")
    spec.subtitles = subs
    out = tmp_path / "cards.ass"
    write_ass(spec, out)
    text = out.read_text(encoding="utf-8")
    assert "Style: Card" in text
    assert "m 0 0 l 1080 0 1080 1920 0 1920" in text     # 풀스크린 어둡게 덮기
    assert "&HFF8D4D&" in text                            # #4D8DFF 강조색 (BGR)
    assert text.count("Dialogue: 5,") == 1 and text.count("Dialogue: 6,") == 1
    # 카드 문장은 강조 태그로 감싸여 들어가고(숫자 앞뒤로 쪼개짐) 2줄(\N) 배치
    assert "만 넘는" in text and "\\N" in text
    # 나머지 문장은 일반 자막 그대로
    assert ",Default,,0,0,0,,첫 문장" in text
    events = [l for l in text.splitlines() if ",Default," in l and "둘째" in l]
    assert not events                                     # 카드로 대체된 문장


def test_write_ass_cards_off_and_marker_stripped(tmp_path):
    spec = make_valid_spec()
    subs = list(spec.subtitles)
    subs[1] = dataclasses.replace(subs[1], text="[카드]95% 만 기억하세요")
    spec.subtitles = subs
    spec.style = dataclasses.replace(spec.style, text_cards=False)
    out = tmp_path / "off.ass"
    write_ass(spec, out)
    text = out.read_text(encoding="utf-8")
    assert "Dialogue: 6," not in text                     # 꺼짐 — 카드 없음
    assert "[카드]" not in text                            # 표식은 화면에 안 나옴
    assert "95% 만 기억하세요" in text                     # 일반 자막으로 표시


def test_tts_never_reads_card_marker():
    src = open("cutdaejang/core/tts_engine.py", encoding="utf-8").read()
    assert 'text.replace("[카드]", " ")' in src
    # 발음 변환은 표식과 무관하게 동작
    from cutdaejang.utils.pronounce import pronounce_ko

    assert pronounce_ko("95% 만") == "구십오퍼센트 만"


@pytest.fixture()
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v107")
    iso = tmp_path_factory.mktemp("iso107")
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


def test_draft_roundtrip(server):
    def post(path, body):
        req = urllib.request.Request(server + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:  # noqa: F821 — urllib.error via urllib.request
            return json.loads(e.read())

    d = post("/api/draft", {"card": "shop",
                            "data": {"shopPasteText": "쓰다 만 상품 설명",
                                     "shopHook": "임시 훅"}})
    assert d.get("ok"), d
    with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
        st = json.loads(r.read())
    saved = ((st.get("settings") or {}).get("ui") or {}).get("drafts", {}).get("shop", {})
    assert saved.get("shopPasteText") == "쓰다 만 상품 설명"
    assert "error" in post("/api/draft", {"data": {}})    # card 없으면 400


def test_v107_ui_wiring():
    html = webui._HTML
    for tok in ('id="setTextCards"', "text_cards: $('setTextCards').checked",
                "s.subtitle.text_cards !== false",
                "DRAFT_FIELDS", "function draftSave", "function bindDrafts",
                "function restoreDrafts", "/api/draft",
                "이어서 작성하던 내용"):
        assert tok in html, tok
    from cutdaejang import config as cfg

    assert cfg.DEFAULTS["subtitle"].get("text_cards") is True
