"""Owner-auth helpers: caller-ID whitelist + fuzzy passphrase match."""
from __future__ import annotations

from typing import Iterable, Optional

from rapidfuzz import fuzz


def is_owner_caller(caller_id: Optional[str], whitelist: Iterable[str]) -> bool:
    if not caller_id:
        return False
    return caller_id in set(whitelist)


def passphrase_match(heard: str, expected: str, threshold: int = 75) -> bool:
    if not heard or not expected:
        return False
    a = heard.strip().lower()
    b = expected.strip().lower()
    score = max(fuzz.WRatio(a, b), fuzz.partial_ratio(a, b))
    return score >= threshold
