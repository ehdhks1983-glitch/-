"""v1.02 — 📈 업로드 키트 알고리즘 전략화 (사용자 리포트 "10일 올려도 조회수 0").

원인 교정: 작은 채널이 "꿀팁·정리" 같은 대중 키워드로는 노출 자체가 안 된다.
→ 틈새 롱테일 검색어 중심 생성 + 채널 단계(신규/성장/정착)별 배합 +
📌 고정 댓글(초기 참여 신호) + 플랫폼별 검색 인덱싱 규칙(틱톡·인스타 캡션 SEO,
네이버 검색어 스타일 태그) + 화면에 문구 밖 4대 요인 안내.
"""

import inspect

from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui


def test_kit_prompt_encodes_algorithm_strategy():
    pr = sg.UPLOAD_KIT_PROMPT
    for tok in ("틈새", "롱테일", "범용 단어만으로 된 제목·태그 금지",
                "niche_keywords", "pinned_comment", "앞 20자",
                "검색에 그대로 인덱싱", "인스타 검색에 인덱싱",
                "네이버에 검색할 법한 명사구", "시의성"):
        assert tok in pr, tok
    # 채널 단계 3종 — 단계별 키워드 배합 지시
    assert set(sg.KIT_STAGE_NOTES) == {"신규", "성장", "정착"}
    assert "틈새 검색어 중심" in sg.KIT_STAGE_NOTES["신규"]
    assert "7 : 대중 키워드 3" in sg.KIT_STAGE_NOTES["성장"]
    # stage 인자가 프롬프트에 꽂힌다
    assert "stage" in inspect.signature(sg.suggest_upload_kit).parameters
    assert "{stage}" in pr


def test_normalize_kit_new_fields_and_caps():
    out = sg.normalize_kit({
        "niche_keywords": [f" #검색어{i} " for i in range(12)],
        "pinned_comment": "질" * 300,
        "titles": ["t"], "tags": [], "keywords": [],
    })
    assert len(out["niche_keywords"]) == 8            # 8개 제한
    assert out["niche_keywords"][0] == "#검색어0"      # strip (＃는 검색어 문장형이라 유지)
    assert len(out["pinned_comment"]) == 200          # 길이 제한
    # 필드가 아예 없어도 안전한 기본값
    empty = sg.normalize_kit({})
    assert empty["niche_keywords"] == [] and empty["pinned_comment"] == ""


def test_kit_stub_has_niche_and_pinned_both_shapes():
    for is_shorts in (True, False):
        kit = sg.suggest_upload_kit_stub("테스트 대본입니다", "청소기 추천",
                                         is_shorts=is_shorts)
        assert kit["niche_keywords"], is_shorts
        assert kit["pinned_comment"], is_shorts
        # 틈새 검색어는 문장형(공백 포함) — 단어 나열이 아니라 실제 검색어 모양
        assert any(" " in k for k in kit["niche_keywords"]), kit["niche_keywords"]


def test_v102_ui_and_route_wiring():
    html = webui._HTML
    for tok in ('id="kitNiche"', 'id="kitPinned"', 'id="setChStage"',
                'id="kitAlgoTips"', "틈새 검색어(노출 시작점)",
                "copyKit(event,'kitPinned')", "조회수가 안 나올 때",
                "stage: $('setChStage').value", "ch.stage"):
        assert tok in html, tok
    src = open(webui.__file__, encoding="utf-8").read()
    assert 'stage=str(channel.get("stage") or "")' in src   # 설정 → 프롬프트 전달
    # 업로드킷.txt에도 틈새 검색어·고정 댓글 섹션이 실린다
    body = src.split("def _kit_text")[1].split("\ndef ")[0]
    assert "niche_keywords" in body and "pinned_comment" in body


def test_kit_text_includes_new_sections():
    kit = sg.suggest_upload_kit_stub("대본", "무선 청소기", is_shorts=True)
    kit["checklist"] = []
    txt = webui._kit_text(kit, "무선 청소기 영상")
    assert "틈새 검색어" in txt and "고정 댓글" in txt
    assert kit["pinned_comment"] in txt
