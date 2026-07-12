"""한글 발음 표기 치환 — TTS 오독 방지 (기획안 §6 탭②, §7-6).

숫자·단위·영어 약어를 한글 읽기로 바꾼다. 검토 화면의 [발음 변환] 버튼이 호출하며,
자동 치환은 하지 않는다(엔진 자체 숫자 읽기가 대체로 정확해 무조건 변환이 오히려
오독을 만들 수 있음 — 사용자가 결과를 보고 확정하는 흐름).

규칙 요약:
  - 한자어 수사(sino): 년·월·일·분·초·원·퍼센트·미터 등 → 이천이십육년, 삼십분
    (6월=유월, 10월=시월 예외 처리)
  - 고유어 수사(native): 개·명·살·번·시·마리·가지 등 → 열두시, 스물한살 (1~99)
  - 소수: 3.5 → 삼점오
  - 영어 대문자 약어(2자 이상): AI → 에이아이, SNS → 에스엔에스
"""

from __future__ import annotations

import re

_SINO_DIGITS = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_SINO_SMALL_UNITS = ["", "십", "백", "천"]
_SINO_BIG_UNITS = ["", "만", "억", "조"]


def sino(n: int) -> str:
    """정수 → 한자어 읽기. 0=영, 10000=만, 20260000=이천이십육만."""
    if n < 0:
        return "마이너스 " + sino(-n)
    if n == 0:
        return "영"
    groups = []
    while n > 0:
        groups.append(n % 10_000)
        n //= 10_000
    parts = []
    for gi in range(len(groups) - 1, -1, -1):
        g = groups[gi]
        if g == 0:
            continue
        text = ""
        for pos in range(3, -1, -1):
            d = (g // (10**pos)) % 10
            if d == 0:
                continue
            digit = _SINO_DIGITS[d]
            if d == 1 and pos > 0:
                digit = ""  # 일십/일백/일천 → 십/백/천
            text += digit + _SINO_SMALL_UNITS[pos]
        if gi == 1 and text == "일":
            text = ""  # 일만 → 만 (단, 일억·일조는 유지)
        parts.append(text + _SINO_BIG_UNITS[gi])
    return "".join(parts)


_NATIVE_TENS = {10: "열", 20: "스물", 30: "서른", 40: "마흔", 50: "쉰",
                60: "예순", 70: "일흔", 80: "여든", 90: "아흔"}
# 단위 앞 관형형 (한 개, 두 명, 스무 살)
_NATIVE_DET_ONES = {0: "", 1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯",
                    6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉"}


def native_det(n: int) -> str:
    """1~99 → 단위 명사 앞 고유어 관형형 (12 → 열두, 21 → 스물한, 20 → 스무)."""
    if not (1 <= n <= 99):
        return sino(n)
    tens, ones = divmod(n, 10)
    if n == 20:
        return "스무"
    prefix = _NATIVE_TENS.get(tens * 10, "") if tens else ""
    return prefix + _NATIVE_DET_ONES[ones]


# 고유어로 세는 단위 (뒤에 조사가 이어져도 매칭되도록 단위만 캡처)
_NATIVE_COUNTERS = "개|명|살|번|시간|시|마리|가지|잔|권|병|편|곡|줄|칸|봉지|그릇|송이"
# 한자어로 읽는 단위 — "개월"은 "개"보다 먼저 매칭되도록 사이노에 배치 (삼개월)
_SINO_UNITS = (
    "개월|년도|년|월|일|분기|분|초|원|퍼센트|프로|밀리미터|센티미터|킬로미터|미터|밀리그램|"
    "킬로그램|그램|킬로|리터|밀리|인치|층|호|동|페이지|쪽|점|도|배|회|차|주년|주차|주|"
    "등|위|단계|세대|세|킬로바이트|메가바이트|기가바이트|바이트|헤르츠|와트|볼트|칼로리"
)
_MONTH_SPECIAL = {6: "유", 10: "시"}  # 6월=유월, 10월=시월

_LETTER_KO = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠",
    "N": "엔", "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티",
    "U": "유", "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}

# 개월은 사이노(삼 개월)라 고유어 목록에서 우선 분리 처리
# \b는 한글 앞뒤에서 성립하지 않으므로("AI가") 영문자 인접만 배제하는 룩어라운드 사용
_RE_ACRONYM = re.compile(r"(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])")
_RE_DECIMAL_UNIT = re.compile(rf"(\d+)\.(\d+)\s?(?:({_SINO_UNITS})|%)")
_RE_DECIMAL = re.compile(r"(\d+)\.(\d+)")
_RE_MONTH = re.compile(r"(?<![\d.])(\d{1,2})월")
_RE_NATIVE = re.compile(rf"(?<![\d.])(\d{{1,2}})\s?({_NATIVE_COUNTERS})")
_RE_SINO_UNIT = re.compile(rf"(?<![\d.])([\d,]+)\s?(?:({_SINO_UNITS})|%)")
_RE_BARE_NUMBER = re.compile(r"(?<![\d.,])([\d,]{1,15})(?![\d.,])")


def _digits(raw: str) -> int:
    return int(raw.replace(",", ""))


def pronounce_ko(text: str) -> str:
    """문장 속 숫자·단위·영문 약어를 한글 발음 표기로 치환."""
    out = text

    out = _RE_ACRONYM.sub(lambda m: "".join(_LETTER_KO[c] for c in m.group(0)), out)

    def decimal_unit(m):
        unit = m.group(3) or "퍼센트"
        return f"{sino(_digits(m.group(1)))}점{''.join(_SINO_DIGITS[int(d)] if d != '0' else '영' for d in m.group(2))}{unit}"

    out = _RE_DECIMAL_UNIT.sub(decimal_unit, out)
    out = _RE_DECIMAL.sub(
        lambda m: f"{sino(_digits(m.group(1)))}점"
        + "".join(_SINO_DIGITS[int(d)] if d != "0" else "영" for d in m.group(2)),
        out,
    )

    def month(m):
        n = int(m.group(1))
        if n in _MONTH_SPECIAL:
            return _MONTH_SPECIAL[n] + "월"
        return sino(n) + "월"

    out = _RE_MONTH.sub(month, out)

    # "개월"이 고유어 "개"에 잡히지 않도록 개월 먼저 한자어 처리됨(_SINO_UNITS에 포함,
    # 아래 고유어 정규식은 그 뒤에 돌므로 남은 "개"만 매칭)
    out = _RE_SINO_UNIT.sub(
        lambda m: sino(_digits(m.group(1))) + (m.group(2) or "퍼센트"), out
    )
    out = _RE_NATIVE.sub(lambda m: native_det(int(m.group(1))) + m.group(2), out)
    out = _RE_BARE_NUMBER.sub(lambda m: sino(_digits(m.group(1))), out)
    return out
