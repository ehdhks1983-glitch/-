"""🅰 텍스트 카드 장면 (v1.11) — 대본 의미에 맞춘 숏폼 장면 자동 연출.

숫자 한 종류만 반복하던 v1.07 카드를 숫자·펀치·목록·비교·후기·검색·단계·
CTA 8종으로 확장한다. 타임라인에 클립을 끼워 넣지 않고 해당 문장 구간에
ASS 오버레이를 얹으므로 영상 길이·내레이션·자막 싱크는 바뀌지 않는다.

규칙:
  - 수동: ``[카드]`` 또는 ``[카드:후기]``처럼 장면 종류까지 지정
  - 자동: 문장을 의미별로 분류하고 같은 종류·인접 카드의 반복을 피함
  - 카드 수: 영상 길이와 다양성(적게/자동/풍부)에 맞춰 자동 조절
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil
from typing import List, Optional

CARD_MARK = "[카드]"
CARD_KINDS = ("number", "punch", "checklist", "compare",
              "review", "search", "steps", "cta")
CARD_KIND_KO = {
    "숫자": "number", "통계": "number",
    "펀치": "punch", "강조": "punch",
    "목록": "checklist", "체크": "checklist", "체크리스트": "checklist",
    "비교": "compare", "대조": "compare",
    "후기": "review", "리뷰": "review",
    "검색": "search", "질문": "search",
    "단계": "steps", "순서": "steps",
    "cta": "cta", "씨티에이": "cta", "구매": "cta",
}

_NUM_RE = re.compile(r"\d[\d,.]*\s*(?:%|퍼센트|만|천|억|원|배|년|개|명|위|배속|시간|분|초|kg|g|cm|mm)")
_BIG_NUM_RE = re.compile(r"\d[\d,.]*\s*%|\d{2,}[\d,.]*")
_MARK_RE = re.compile(r"^\s*\[카드(?:\s*:\s*([^\]]+))?\]\s*", re.I)
_NO_CARD_RE = re.compile(r"^\s*\[(?:일반|자막)\]\s*")
_QUESTION_RE = re.compile(r"[?？]|(?:왜|어떻게|무엇|뭘|궁금|알고\s*계|찾고\s*계)")
_COMPARE_RE = re.compile(r"\bvs\.?\b|비교|차이|반면|반대로|보다|기존|전후|장단점", re.I)
_REVIEW_RE = re.compile(r"후기|리뷰|별점|만족|써\s*보니|사용해\s*보니|추천|재구매|솔직")
_STEPS_RE = re.compile(r"(?:\d+\s*단계|첫째|둘째|셋째|먼저|다음으로|마지막으로|순서|방법)")
_CHECK_RE = re.compile(r"(?:\d+\s*가지|핵심|포인트|체크|준비물|주의사항|꼭\s*기억)")
_CTA_RE = re.compile(r"지금|링크|구매|주문|신청|확인해|눌러|구독|팔로우|저장|댓글|공유|프로필")
_PUNCH_RE = re.compile(r"단\s*하나|결론|중요|절대|진짜|바로\s*이것|놀라운|이것만|한마디로")


@dataclass(frozen=True)
class CardChoice:
    """자막 번호와 그 구간에 사용할 장면 템플릿."""

    index: int
    kind: str
    manual: bool = False


def is_marked(text: str) -> bool:
    return bool(_MARK_RE.match(text or ""))


def strip_mark(text: str) -> str:
    t = _MARK_RE.sub("", text or "", count=1)
    return _NO_CARD_RE.sub("", t, count=1).strip()


def is_no_card(text: str) -> bool:
    """사용자가 이 줄을 일반 자막으로 고정했는지."""
    return bool(_NO_CARD_RE.match(text or ""))


def marked_kind(text: str) -> str:
    """``[카드:후기]``의 종류를 내부 이름으로. 단순 ``[카드]``면 빈 문자열."""
    m = _MARK_RE.match(text or "")
    if not m or not m.group(1):
        return ""
    raw = m.group(1).strip().lower()
    return raw if raw in CARD_KINDS else CARD_KIND_KO.get(raw, "")


def _clean_len(text: str) -> int:
    """색 마크업·공백 빼고 실제 글자 수."""
    t = re.sub(r"\[[/가-힣A-Za-z]*\]", "", text or "")
    return len(t.replace(" ", ""))


def _auto_score(text: str) -> int:
    """v1.07 호환 후보 점수 — 공개 함수 ``pick_card_indices``의 기존 동작용."""
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
    """기존 API: 문장 목록 → 카드 번호. v1.07의 최대 4장 규칙을 보존한다."""
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


def classify_card(text: str, content_pack: str = "auto") -> str:
    """문장 의미를 8개 장면 템플릿 중 하나로 분류한다."""
    explicit = marked_kind(text)
    if explicit:
        return explicit
    t = strip_mark(text).strip()
    if _NUM_RE.search(t):
        return "number"
    if _REVIEW_RE.search(t):
        return "review"
    if _QUESTION_RE.search(t):
        return "search"
    if _COMPARE_RE.search(t):
        return "compare"
    if _STEPS_RE.search(t):
        return "steps"
    if _CHECK_RE.search(t):
        return "checklist"
    if _CTA_RE.search(t):
        return "cta"
    # 애매한 짧은 문장은 콘텐츠 성격에 맞는 카드로 보정한다.
    n = _clean_len(t)
    pack = (content_pack or "auto").lower()
    if n <= 18 and pack in ("shopping", "쇼핑"):
        return "cta" if _CTA_RE.search(t) else "punch"
    if n <= 22 and pack in ("review", "리뷰"):
        return "review"
    if n <= 22 and pack in ("info", "정보"):
        return "checklist"
    return "punch"


def _semantic_score(text: str, kind: str, content_pack: str) -> int:
    """자동 카드 후보 우선순위. 명시 표시는 가장 높은 점수."""
    if is_marked(text):
        return 100
    t = strip_mark(text)
    n = _clean_len(t)
    if not t.strip() or n > 48:
        return 0
    score = 0
    if kind == "number" and _NUM_RE.search(t):
        score = 7
    elif kind == "review" and _REVIEW_RE.search(t):
        score = 6
    elif kind == "compare" and _COMPARE_RE.search(t):
        score = 6
    elif kind == "search" and _QUESTION_RE.search(t):
        score = 6
    elif kind == "steps" and _STEPS_RE.search(t):
        score = 5
    elif kind == "checklist" and _CHECK_RE.search(t):
        score = 5
    elif kind == "cta" and _CTA_RE.search(t):
        score = 5
    elif kind == "punch" and _PUNCH_RE.search(t):
        score = 4
    elif 2 <= n <= 16:
        score = 2
    elif n <= 26:
        score = 2

    pack = (content_pack or "auto").lower()
    preferred = {
        "shopping": {"number", "review", "compare", "cta"},
        "쇼핑": {"number", "review", "compare", "cta"},
        "info": {"number", "search", "steps", "checklist", "compare"},
        "정보": {"number", "search", "steps", "checklist", "compare"},
        "review": {"review", "compare", "number"},
        "리뷰": {"review", "compare", "number"},
        "promo": {"punch", "number", "cta", "compare"},
        "홍보": {"punch", "number", "cta", "compare"},
    }.get(pack, set())
    return score + (1 if kind in preferred and score else 0)


def card_limit(duration_us: int, text_count: int, density: str = "auto") -> int:
    """영상 길이·문장 수에 따른 카드 상한.

    30초 약 3장, 60초 약 5장, 긴 영상은 최대 24장으로 제한한다.
    인접 카드를 피하므로 실제 수는 이보다 적을 수 있다.
    """
    if text_count <= 0:
        return 0
    sec = max(1.0, float(duration_us or 0) / 1_000_000)
    base = max(1, min(24, ceil(sec / 12.0)))
    d = (density or "auto").lower()
    if d in ("low", "적게"):
        base = max(1, ceil(base * 0.6))
    elif d in ("rich", "풍부", "풍부하게"):
        base = min(30, ceil(base * 1.45))
    # 연속 카드를 막는 구조에서 현실적으로 가능한 수 이상은 요구하지 않는다.
    return min(base, max(1, (text_count + 1) // 2))


def pick_card_plan(
    texts: List[str],
    duration_us: int = 0,
    density: str = "auto",
    content_pack: str = "auto",
    max_cards: Optional[int] = None,
) -> List[CardChoice]:
    """대본 전체에서 의미·간격·종류 반복을 고려한 카드 배치표를 만든다."""
    if not texts:
        return []
    limit = (max(0, int(max_cards)) if max_cards is not None
             else card_limit(duration_us, len(texts), density))
    if limit <= 0:
        return []

    manual = [
        CardChoice(i, marked_kind(t) or classify_card(t, content_pack), True)
        for i, t in enumerate(texts) if is_marked(t)
    ]
    # 자막 한 줄짜리 클립은 그 한 줄 자체가 본문이다. 자동으로 풀스크린 카드로
    # 바꾸면 위치 조정·일반 자막 편집이 사라지므로 수동 표시가 있을 때만 카드화.
    if len(texts) < 2 and not manual:
        return []
    # 수동 지정은 사용자의 의도를 우선하되 비정상적으로 많으면 안전 상한까지만.
    picked = list(manual[:max(limit, min(len(manual), 30))])
    if len(picked) >= limit:
        return sorted(picked, key=lambda c: c.index)

    ranked = []
    for i, text in enumerate(texts):
        if is_marked(text) or is_no_card(text):
            continue
        kind = classify_card(text, content_pack)
        if len(texts) < 3 and kind in ("punch", "steps", "checklist"):
            continue
        score = _semantic_score(text, kind, content_pack)
        if score >= 3:
            ranked.append((score, i, kind))
    ranked.sort(key=lambda x: (-x[0], x[1]))

    for _score, i, kind in ranked:
        if len(picked) >= limit:
            break
        if any(abs(i - p.index) <= 1 for p in picked):
            continue
        # 같은 템플릿이 가까운 장면에서 반복되면 단조로우므로 한 번 건너뛴다.
        if any(p.kind == kind and abs(i - p.index) <= 4 for p in picked):
            continue
        picked.append(CardChoice(i, kind, False))

    # 종류 제한 때문에 빈자리가 남으면 간격만 지키고 채운다.
    if len(picked) < limit:
        for _score, i, kind in ranked:
            if len(picked) >= limit:
                break
            if any(i == p.index or abs(i - p.index) <= 1 for p in picked):
                continue
            picked.append(CardChoice(i, kind, False))
    return sorted(picked, key=lambda c: c.index)


def accent_spans(text: str):
    """카드 글에서 강조색으로 칠할 (시작, 끝) 문자 범위 — 숫자·% 덩어리."""
    return [(m.start(), m.end()) for m in _BIG_NUM_RE.finditer(text or "")]
