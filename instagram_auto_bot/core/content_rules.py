"""Content compliance rules (Section 3 of the spec) - pure, Tk-free, testable.

Enforces:
* Banned vocabulary (medical-authority claims + associative terms + user extras).
* Exactly ``IG_HASHTAG_COUNT`` hashtags (truncate excess, pad shortfall from a
  rotation pool, drop duplicates / banned / spam tags).
* Caption length / composition (<= 2200 chars, keyword front-loading hook).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

import config

# A hashtag: '#', then any run of non-space, non-punctuation chars.
HASHTAG_RE = re.compile(r"#[^\s#.,!?　]+")


# --------------------------------------------------------------------------- #
# Hashtag helpers
# --------------------------------------------------------------------------- #
def extract_hashtags(text: str) -> List[str]:
    return HASHTAG_RE.findall(text or "")


def strip_hashtags(text: str) -> str:
    return HASHTAG_RE.sub("", text or "").strip()


def normalize_hashtag(tag: str) -> str:
    """Return a canonical ``#tag`` form (single leading #, no inner spaces)."""
    if not tag:
        return ""
    t = tag.strip().lstrip("#")
    t = re.sub(r"\s+", "", t)
    return f"#{t}" if t else ""


# --------------------------------------------------------------------------- #
# Banned words
# --------------------------------------------------------------------------- #
def parse_extra_banned(raw: str) -> List[str]:
    """Split a user 'banned expressions' field (comma / newline separated)."""
    if not raw:
        return []
    return [p.strip() for p in re.split(r"[,\n]", raw) if p.strip()]


def _banned_words(extra: Optional[Iterable[str]] = None) -> List[str]:
    words = list(config.BANNED_WORDS_EXTENDED)
    if extra:
        words += [w.strip() for w in extra if w and w.strip()]
    return words


def find_banned_words(text: str, extra: Optional[Iterable[str]] = None) -> List[str]:
    """Return the banned words present in ``text`` (case-insensitive, deduped)."""
    if not text:
        return []
    low = text.lower()
    seen: set[str] = set()
    out: List[str] = []
    for w in _banned_words(extra):
        wl = w.lower()
        if wl and wl in low and wl not in seen:
            seen.add(wl)
            out.append(w)
    return out


def is_banned_hashtag(tag: str, extra_banned: Optional[Iterable[str]] = None) -> bool:
    norm = normalize_hashtag(tag).lower()
    if not norm:
        return True
    if norm in {b.lower() for b in config.BANNED_HASHTAGS}:
        return True
    inner = norm.lstrip("#")
    return any(w.lower() in inner for w in _banned_words(extra_banned) if w)


def enforce_hashtag_count(
    tags: Sequence[str],
    count: Optional[int] = None,
    fill_pool: Optional[Sequence[str]] = None,
    extra_banned: Optional[Iterable[str]] = None,
    rng: Optional[random.Random] = None,
) -> List[str]:
    """Coerce ``tags`` to exactly ``count`` clean hashtags where possible.

    Order of operations: normalize -> dedupe -> drop banned/spam -> truncate to
    ``count`` -> pad from ``fill_pool`` (shuffled for rotation/variety).
    Returns fewer than ``count`` only when the pool cannot supply enough.
    """
    count = count or config.IG_HASHTAG_COUNT
    rng = rng or random

    seen: set[str] = set()
    cleaned: List[str] = []
    for t in tags:
        n = normalize_hashtag(t)
        key = n.lower()
        if not n or n == "#" or key in seen:
            continue
        if is_banned_hashtag(n, extra_banned):
            continue
        seen.add(key)
        cleaned.append(n)

    if len(cleaned) > count:
        return cleaned[:count]

    if len(cleaned) < count and fill_pool:
        pool = []
        for t in fill_pool:
            n = normalize_hashtag(t)
            key = n.lower()
            if n and key not in seen and not is_banned_hashtag(n, extra_banned):
                pool.append(n)
        rng.shuffle(pool)
        for n in pool:
            if len(cleaned) >= count:
                break
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(n)

    return cleaned[:count]


# --------------------------------------------------------------------------- #
# Caption composition
# --------------------------------------------------------------------------- #
def compose_caption(body: str, hashtags: Sequence[str], max_len: Optional[int] = None) -> str:
    """Join body + hashtag block, trimming the body to fit ``max_len``."""
    max_len = max_len or config.CAPTION_MAX_LEN
    body = (body or "").strip()
    tags = " ".join(hashtags).strip()
    if not tags:
        return body[:max_len].rstrip()
    full = f"{body}\n\n{tags}".strip()
    if len(full) <= max_len:
        return full
    room = max_len - (len(tags) + 2)
    if room <= 0:
        return tags[:max_len]
    return f"{body[:room].rstrip()}\n\n{tags}"


@dataclass
class RuleReport:
    ok: bool
    banned_words: List[str] = field(default_factory=list)
    hashtag_count: int = 0
    too_long: bool = False
    hook_ok: bool = True
    notes: List[str] = field(default_factory=list)


def check_caption(
    caption: str,
    hashtags: Sequence[str],
    *,
    expected_count: Optional[int] = None,
    extra_banned: Optional[Iterable[str]] = None,
) -> RuleReport:
    """Validate a finished caption against the content rules."""
    expected_count = expected_count or config.IG_HASHTAG_COUNT
    banned = find_banned_words(caption, extra_banned)
    too_long = len(caption) > config.CAPTION_MAX_LEN
    hook = caption.strip()[: config.CAPTION_HOOK_LEN]
    hook_ok = bool(hook) and not hook.lstrip().startswith("#")
    notes: List[str] = []
    if banned:
        notes.append("금지어 포함: " + ", ".join(banned))
    if len(hashtags) != expected_count:
        notes.append(f"해시태그 {len(hashtags)}개 (목표 {expected_count}개)")
    if too_long:
        notes.append(f"본문 {len(caption)}자 (최대 {config.CAPTION_MAX_LEN}자 초과)")
    if not hook_ok:
        notes.append("첫 문장이 비었거나 해시태그로 시작함")
    ok = not banned and not too_long and hook_ok and len(hashtags) == expected_count
    return RuleReport(ok, banned, len(hashtags), too_long, hook_ok, notes)
