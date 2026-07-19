"""발음 표기 치환 검증 (기획안 탭② 발음 변환 버튼)."""

import pytest

from cutdaejang.utils.pronounce import native_det, pronounce_ko, sino


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "영"), (1, "일"), (10, "십"), (15, "십오"), (110, "백십"),
        (2026, "이천이십육"), (10_000, "만"), (20_000, "이만"),
        (123_456_789, "일억이천삼백사십오만육천칠백팔십구"),
    ],
)
def test_sino(n, expected):
    assert sino(n) == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [(1, "한"), (2, "두"), (3, "세"), (12, "열두"), (20, "스무"), (21, "스물한"), (99, "아흔아홉")],
)
def test_native_det(n, expected):
    assert native_det(n) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026년", "이천이십육년"),
        ("10월 3일", "시월 삼일"),
        ("6월", "유월"),
        ("12시 30분", "열두시 삼십분"),
        ("21살", "스물한살"),
        ("15개", "열다섯개"),
        ("3개월", "삼개월"),
        ("AI가 SNS를 바꿉니다", "에이아이가 에스엔에스를 바꿉니다"),
        ("10%", "십퍼센트"),
        ("3.5배", "삼점오배"),
        ("1,000원", "천원"),
        ("100개", "백개"),
        ("하루 10분 정리", "하루 십분 정리"),
        ("숫자 없는 문장은 그대로", "숫자 없는 문장은 그대로"),
    ],
)
def test_pronounce_ko(text, expected):
    assert pronounce_ko(text) == expected


def test_bare_comma_does_not_crash():
    """v0.46.1 — 맨 쉼표([\\d,]가 ','만 매칭)로 int('') 크래시하던 버그."""
    assert pronounce_ko("정리 습관, 삼십 초만 집중해 주세요.") == "정리 습관, 삼십 초만 집중해 주세요."
    assert pronounce_ko(",") == ","
    assert pronounce_ko("쉼표 1,000원") == "쉼표 천원"  # 진짜 숫자+쉼표는 그대로 동작
