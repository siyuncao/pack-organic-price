"""
A disk cache, so asking the same question twice does not cost two requests.

Prices move slowly and quotas do not. ChemSpace allows 40 requests a minute;
a paper with fifteen compounds, re-run four times while you are working on
something else, is 120 requests for answers that have not changed.

HOW LONG A PRICE STAYS FRESH is a judgement, not a technical fact, so it is
written down here rather than buried. A chemist grading these results scored
them like this:

    quoted today        5
    a month old         4
    two months old      3
    older than that     2

Seven days is the default because it is comfortably inside "today" on that
scale, while still absorbing the repeated runs that happen during a working
session. Set PACKPRICE_CACHE_DAYS to change it, or 0 to switch it off.

WHAT IS NOT CACHED: failures. A timeout is not an answer and must never be
remembered as one. An honest empty result IS cached, because "no supplier
sells this" is a real finding, and the expiry is what stops it being true
forever.

Every cached option carries the time it was retrieved, so a caller can show
the age rather than implying the price is live.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(
    os.environ.get(
        "PACKPRICE_CACHE_DIR",
        Path.home() / ".cache" / "pack-organic-price",
    )
)

try:
    MAX_AGE_DAYS = float(os.environ.get("PACKPRICE_CACHE_DAYS", "7"))
except ValueError:
    MAX_AGE_DAYS = 7.0


def _key(source: str, smiles: str, grams: float, config: str = "") -> str:
    """
    One cache file per distinct question.

    Anything that changes the answer belongs in the key. The amount is
    rounded to a gram because asking for 7.6 g and 7.61 g is the same
    question, and a key that treats them differently caches nothing.
    """
    amount = "any" if not grams else str(int(round(grams)))
    raw = "|".join([source, smiles, amount, config])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def get(source: str, smiles: str, grams: float, config: str = "", now: float = None):
    """
    The cached options for this question, or None if there is no fresh entry.

    None means "ask the marketplace". An empty list means "the marketplace
    was asked, recently, and has nothing" — those are different, in the same
    way a failure and an empty result are different.
    """
    if MAX_AGE_DAYS <= 0:
        return None

    now = time.time() if now is None else now
    path = _path(_key(source, smiles, grams, config))
    try:
        entry = json.loads(path.read_text())
    except (OSError, ValueError):
        return None

    age = now - entry.get("retrieved_at", 0)
    if age > MAX_AGE_DAYS * 86400:
        return None

    return entry.get("options")


def put(source: str, smiles: str, grams: float, options: list, config: str = "",
        now: float = None) -> None:
    """
    Remember a successful answer. Callers must not call this after a failure.

    Writes are best-effort: a cache that cannot be written is a slower
    program, not a broken one, so every filesystem error is swallowed here
    and only here.
    """
    if MAX_AGE_DAYS <= 0:
        return

    now = time.time() if now is None else now
    stamped = [dict(o, retrieved_at=now) for o in options]
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path(_key(source, smiles, grams, config)).write_text(
            json.dumps({"retrieved_at": now, "options": stamped})
        )
    except OSError:
        pass


def age_days(option: dict, now: float = None) -> Optional[float]:
    """How old this price is, or None if it came back live."""
    stamp = option.get("retrieved_at")
    if stamp is None:
        return None
    now = time.time() if now is None else now
    return (now - stamp) / 86400


def clear() -> int:
    """Delete every cached entry. Returns how many files were removed."""
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
