"""v1.03 — 🔤 GIF를 '지프'가 아니라 '지아이에프'로 (한국식 이니셜 읽기, 사용자 리포트).

대문자 약어 규칙([A-Z]{2,})만 있어 소문자 gif·숫자 섞인 mp3가 새던 구멍을
기술 용어 사전(대소문자 무관)으로 막는다. 자막은 원문 그대로, TTS 소리만 변환.
"""

import pytest

from cutdaejang.utils.pronounce import pronounce_ko


@pytest.mark.parametrize("text,expected", [
    ("GIF 만드는 법", "지아이에프 만드는 법"),           # 대문자 (기존 규칙과 동일 결과)
    ("gif 파일이에요", "지아이에프 파일이에요"),          # 🐞 소문자 — 리포트 케이스
    ("Gif도 됩니다", "지아이에프도 됩니다"),             # 혼합 표기
    ("mp3 플레이어", "엠피쓰리 플레이어"),               # 숫자 섞임 — 엠피삼 방지
    ("MP4로 저장", "엠피포로 저장"),
    ("wifi 연결", "와이파이 연결"),
    ("Wi-Fi 비밀번호", "와이파이 비밀번호"),
    ("pdf 정리", "피디에프 정리"),
    ("ai가 sns를 바꿔요", "에이아이가 에스엔에스를 바꿔요"),
])
def test_tech_terms_read_korean_initials(text, expected):
    assert pronounce_ko(text) == expected


def test_tech_terms_do_not_touch_real_words():
    """영단어 일부·긴 단어는 건드리지 않는다 (경계 가드)."""
    assert pronounce_ko("gift 아이디어") == "gift 아이디어"      # gif+t — 단어 일부
    assert pronounce_ko("Airpods 소개") == "Airpods 소개"        # ai+rpods
    assert pronounce_ko("아이디어 회의") == "아이디어 회의"        # 한글은 그대로
    assert "지아이에프" in pronounce_ko("움짤(GIF) 저장법")       # 괄호 안 약어는 변환


def test_auto_pronounce_hooked_into_tts_path():
    """모든 목소리 합성이 지나는 synth_sentence에서 자동 적용 (v0.46.1 경로 확인)."""
    src = open("cutdaejang/core/tts_engine.py", encoding="utf-8").read()
    body = src.split("def synth_sentence")[1].split("\n    def ")[0]
    assert "_pronounced" in body
    pr = open("cutdaejang/utils/pronounce.py", encoding="utf-8").read()
    assert "_TECH_TERMS" in pr and '"gif": "지아이에프"' in pr
