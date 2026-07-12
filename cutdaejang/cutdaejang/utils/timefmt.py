"""시간 단위 변환 — 전 모듈 공통 규칙: 내부 시간은 항상 μs 정수 (기획안 §7-2)."""

US_PER_SECOND = 1_000_000


def us_to_ass(us: int) -> str:
    """μs → ASS 타임스탬프 ``H:MM:SS.CC`` (센티초 내림).

    내림을 쓰는 이유: 종료 시각이 다음 자막 시작 위로 넘치지 않게 하기 위함.
    """
    if us < 0:
        raise ValueError(f"음수 시간은 허용되지 않음: {us}")
    cs = us // 10_000
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def us_to_seconds_str(us: int) -> str:
    """μs → FFmpeg 인자용 초 문자열 (소수 6자리, 정밀도 손실 없음)."""
    if us < 0:
        raise ValueError(f"음수 시간은 허용되지 않음: {us}")
    return f"{us // US_PER_SECOND}.{us % US_PER_SECOND:06d}"


def us_to_samples(us: int, sample_rate: int = 48_000) -> int:
    """μs → 오디오 샘플 수 (adelay 샘플 단위 지연용, 반올림)."""
    return round(us * sample_rate / US_PER_SECOND)


def seconds_to_us(seconds: float) -> int:
    """초(float, ffprobe 실측값) → μs 정수 (반올림)."""
    return round(seconds * US_PER_SECOND)
