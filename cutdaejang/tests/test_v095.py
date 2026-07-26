"""v0.95 — 🎙 구간 목소리 전체 대본 일괄 합성 + 🎵 '음악' 자막 환각 필터 + 재편집 가드."""

from cutdaejang.gui import webui


def test_music_caption_hallucinations_filtered():
    """BGM 구간을 '[음악]'·'박수' 등으로 받아적는 환각이 자막에 실리지 않는다."""
    from cutdaejang.core.stt_engine import is_hallucination

    for t in ("음악", "[음악]", "(음악)", " 음악 ", "배경음악", "박수", "웃음",
              "노래", "BGM", "bgm", "♪", "신나는 음악"):
        assert is_hallucination(t), t
    # 실제 말은 그대로 살아야 한다 — 음악이 '포함'된 문장은 환각이 아님
    for t in ("이 음악 프로그램은 정말 편해요", "박수 쳐 주세요 여러분",
              "오늘의 핵심 정리입니다"):
        assert not is_hallucination(t), t


def test_sections_tts_one_batch_wiring():
    """구간 목소리는 전체 대본을 한 번에 합성해 문장별로 나눠 쓴다 (톤 이어짐)."""
    src = open(webui.__file__, encoding="utf-8").read()
    assert "전체 대본" in src and "clip_slices" in src
    # 구간 루프 안 per-구간 synth 호출이 사라지고 일괄 호출 1곳만 남는다
    body = src.split("def _run_sections")[1].split("\ndef ")[0]
    assert body.count("synth_with_fallback(") == 1
    assert "구간이 넘어가도 톤이 이어져요" in body


def test_v095_reedit_and_silence_guards():
    html = webui._HTML
    for tok in (
        # 완성본 재편집 경고 (글씨 겹침·내레이션 사라짐 방지)
        "isCutOutput", "이미 완성한 영상", "원본 영상을 골라주세요",
        # 완성본 재편집 시 무음 방지 — 원본 소리 자동 켬
        "완성본의 목소리가 사라지지 않게",
        # 일반 편집 무음 결과 사전 확인
        "소리가 하나도 없는 영상",
    ):
        assert tok in html, tok
