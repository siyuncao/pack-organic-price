"""
One definition of "cheapest way to get enough", shared by everything.

This lived inside __init__.py, where the merge could see it and the vendor
modules could not. So chemspace.py grew its own rule — keep the packs closest
in SIZE to what is needed — and truncated on that before the merge ever ran.
Two criteria, applied in sequence, and the second could not see what the first
had thrown away.

Measured on eight compounds from the benchmark, that lost the cheapest buy on
four of them:

    Et3N          kept $4.60 for 10 g, discarded $3.45 for 100 g
    1 M HCl       kept $10.35 for 25 g, discarded $3.45 for 100 g
    pyrrolidine   kept $14.30 for 5 g, which needs two packs, over
                  $24.20 for 25 g, which needs one

The rule for truncating and the rule for ranking have to be the same rule, so
it lives here and both import it.
"""

import math
import re
from typing import Optional

# Pack units that can be compared with an amount in grams. A bottle quoted in
# millilitres cannot, without a density this package does not have.
TO_GRAMS = {"g": 1.0, "mg": 0.001, "kg": 1000.0}


def price_of(option: dict) -> Optional[float]:
    """
    The number in a price string, or None.

    Suppliers write prices in prose: "$84.85 / Each of 1", "USD 56.60",
    "$1,299". A string this cannot read returns None and sorts last, rather
    than crashing a run over one bad row.
    """
    match = re.search(r"[\d,]+\.?\d*", str(option.get("price") or ""))
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def grams_of(option: dict) -> Optional[float]:
    """Pack size in grams, or None when it is quoted by volume."""
    scale = TO_GRAMS.get(str(option.get("pack_size_unit") or "").lower())
    amount = option.get("pack_size_amount")
    return amount * scale if scale and amount is not None else None


def total_cost(option: dict, grams: float = None) -> tuple:
    """
    What this offer costs to satisfy the need, as a sort key.

    Packs are indivisible, so needing 30 g of something sold in 25 g bottles
    means buying two. The comparison is between total prices paid, not unit
    prices: a lower price per gram on a pack you must buy three of is not
    cheaper.

    Returns a tuple so unusable offers sort last rather than crashing the run:
    no price, or a pack quoted by volume when the need is a mass.
    """
    price = price_of(option)
    pack = grams_of(option)

    if price is None:
        return (2, float("inf"))
    if grams is None or pack is None or pack <= 0:
        return (1, price)

    packs = max(1, math.ceil(grams / pack))
    return (0, packs * price)
