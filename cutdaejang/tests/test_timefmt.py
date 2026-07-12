import pytest

from cutdaejang.utils.timefmt import (
    seconds_to_us,
    us_to_ass,
    us_to_samples,
    us_to_seconds_str,
)


def test_us_to_ass_basic():
    assert us_to_ass(0) == "0:00:00.00"
    assert us_to_ass(300_000) == "0:00:00.30"
    assert us_to_ass(3_100_000) == "0:00:03.10"
    assert us_to_ass(58_200_000) == "0:00:58.20"
    assert us_to_ass(3_661_010_000) == "1:01:01.01"


def test_us_to_ass_floors_centiseconds():
    # 9999μs 남는 부분은 내림 → 다음 자막과 겹치지 않게
    assert us_to_ass(1_239_999) == "0:00:01.23"


def test_us_to_ass_rejects_negative():
    with pytest.raises(ValueError):
        us_to_ass(-1)


def test_us_to_seconds_str_precision():
    assert us_to_seconds_str(58_200_000) == "58.200000"
    assert us_to_seconds_str(1) == "0.000001"


def test_us_to_samples_48k():
    assert us_to_samples(1_000_000) == 48_000
    assert us_to_samples(300_000) == 14_400


def test_seconds_to_us_round():
    assert seconds_to_us(1.0000004) == 1_000_000
    assert seconds_to_us(58.2) == 58_200_000
