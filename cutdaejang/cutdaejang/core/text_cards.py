"""🅰 텍스트 카드 장면 (v1.07) — 문장을 풀스크린 타이포 연출로 (사용자 스샷 요청).

"100만과 300만 사이엔 '단 하나의 차이'가 있다" / 파랑 글로우 "95%" 같은
유튜브식 풀스크린 글자 장면. 타임라인에 클립을 끼워 넣는 게 아니라, 해당
문장 구간 동안 화면을 어둡게 덮고 큰 글자를 띄우는 ASS 오버레이라 영상
길이·내레이션·이음새(v1.00 베드)를 전혀 건드리지 않는다 — 그래서 생성·편집·
사진·구간·블로그·쇼핑 여섯 카테고리 전부에 같은 코드로 적용된다.

규칙:
  - 수동: 대본 줄 맨 앞에 [카드] 를 붙이면 그 문장은 무조건 카드 (표시는 제거)
  - 자동: 숫자+단위(%·만·원·배·년·개…)가 든 문장, 또는 14자 이하의 짧은
    펀치 문장을 고른다 — 영상당 최대 4장, 연속 두 문장은 피함
"""

from __future__ import annotations

import re
from typing import List

CARD_MARK = "[카드]"

_NUM_RE = re.compile(r"\d[\d,.]*\s*(?:%|퍼센트|만|천|억|원|배|년|개|명|위|배속|시간|분|초|kg|g|cm|mm)")
_BIG_NUM_RE = re.compile(r"\d[\d,.]*\s*%|\d{2,}[\d,.]*")


def is_marked(text: str) -> bool:
    return (text or "").lstrip().startswith(CARD_MARK)


def strip_mark(text: str) -> str:
    t = (text or "").lstrip()
    return t[len(CARD_MARK):].strip() if t.startswith(CARD_MARK) else (text or "")


def _clean_len(text: str) -> int:
    """색 마크업·공백 빼고 실제 글자 수."""
    t = re.sub(r"\[[/가-힣A-Za-z]*\]", "", text or "")
    return len(t.replace(" ", ""))


def _auto_score(text: str) -> int:
    """카드 후보 점수 — 0이면 후보 아님."""
    t = strip_mark(text)
    if not t.strip():
        return 0
    score = 0
    if _NUM_RE.search(t):
        score += 2                      # 숫자+단위 — 스샷의 95%·300개류
    n = _clean_len(t)
    if 2 <= n <= 14:
        score += 1                      # 짧은 펀치 문장
    if n > 34:
        return 0                        # 긴 문장은 카드로 못 담음 (2줄 초과)
    return score


def pick_card_indices(texts: List[str], max_cards: int = 4) -> List[int]:
    """문장 목록 → 카드로 띄울 번호들. [카드] 수동 표시가 항상 우선."""
    manual = [i for i, t in enumerate(texts) if is_marked(t)]
    picked = list(manual[:max_cards])
    if len(picked) < max_cards:
        cands = sorted(
            ((_auto_score(t), i) for i, t in enumerate(texts)
             if i not in picked and _auto_score(t) >= 2),
            key=lambda x: (-x[0], x[1]))
        for _s, i in cands:
            if len(picked) >= max_cards:
                break
            if any(abs(i - p) <= 1 for p in picked):   # 연속 카드는 답답함 — 띄운다
                continue
            picked.append(i)
    return sorted(picked)


def accent_spans(text: str):
    """카드 글에서 강조색으로 칠할 (시작, 끝) 문자 범위 — 숫자·% 덩어리."""
    return [(m.start(), m.end()) for m in _BIG_NUM_RE.finditer(text or "")]
