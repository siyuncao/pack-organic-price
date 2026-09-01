"""
pack-organic-price — what pack do I buy, and what does it cost.

Chemical marketplaces answer "what does this molecule cost" well. A synthetic
chemist working from a published procedure has a different question: the
paper says 23.6 mL of 10-undecenoyl chloride, so which pack, from whom, and
how much is left in the bottle afterwards.

Those questions look similar and are not. Ask a marketplace the first one and
it will happily quote a 30 mg vial, which is a real price for a quantity
nobody running this reaction can use. So this package puts the AMOUNT NEEDED
into the query, asks every marketplace it has a key for, and returns the
offers in one shape, closest-to-what-you-need first.

    from packprice import find_options
    find_options("Fc1ccccn1", grams=7.6)
    # [{'supplier': 'A2B Chem LLC', 'pack_size_amount': 25.0,
    #   'pack_size_unit': 'g', 'price': '$10', 'source': 'molport', ...}, ...]

Set whichever keys you have; sources without one are skipped silently.

    MOLPORT_API_KEY     https://www.molport.com
    CHEMSPACE_API_KEY   info@chem-space.com
    MCULE_API_KEY       https://mcule.com

COVERAGE is the reason for querying more than one. Measured by hand on the
fifteen orderable compounds of Org. Synth. 2023, 100, 136:

    MolPort      5 / 15    building blocks, best prices when it has them
    ChemSpace   15 / 15    wider catalogue, including TEMPO and zinc dust
                           that MolPort lists as discontinued

Neither is a superset. MolPort beat ChemSpace on price for four of the five
it answered; ChemSpace answered every one MolPort missed. Ask both.

WHAT THIS IS NOT. Bulk solvents and prepared solutions are not marketplace
products. Ask for dichloromethane and you will be offered a 1 g vial, because
building-block catalogues do not stock 2.5 L Winchesters. Ask for "1 M HCl"
and you get the gas. Filter those out before you call this, or accept that a
chemist has to look at the answer.

PRIOR ART. ChemPrice (Sorkun et al., Chemistry-Methods 2025,
github.com/bsaliou/ChemPrice, BSD-3) had the idea of one interface over these
marketplaces first, and this package would not exist without having read it.
It targets drug discovery, quotes at milligram scale, and its ChemSpace
endpoint has returned 404 since their last commit two years ago.
"""

import logging
from typing import Dict, List, NamedTuple, Optional

from . import chemspace, molport
from .errors import SourceError

log = logging.getLogger(__name__)

__version__ = "0.1.0"

SOURCES = {
    "molport": molport,
    "chemspace": chemspace,
}


def _grams(option: dict) -> Optional[float]:
    """Pack size in grams. None when the pack is quoted by volume."""
    scale = {"g": 1.0, "mg": 0.001, "kg": 1000.0}.get(
        str(option.get("pack_size_unit") or "").lower()
    )
    amount = option.get("pack_size_amount")
    return amount * scale if scale and amount is not None else None


def _price(option: dict) -> Optional[float]:
    """
    The number in a price string, or None.

    Suppliers write prices in prose: "$84.85 / Each of 1", "USD 56.60",
    "$1,299". Sorting has to cope with all of them, and a string it cannot
    read sorts last rather than crashing the run.
    """
    import re

    match = re.search(r"[\d,]+\.?\d*", str(option.get("price") or ""))
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def find_options(
    smiles: str,
    grams: float = None,
    name: str = "",
    sources: List[str] = None,
) -> List[dict]:
    """
    Every offer for one compound, from every marketplace with a key set.

    smiles   structure to search for; the only required argument
    grams    how much the procedure needs, used to rank packs by fit
    name     free label, passed to marketplaces that log search names
    sources  restrict to a subset, e.g. ["molport"]. Default is all.

    Each returned dict carries a "source" saying which marketplace answered,
    so a caller can tell a marketplace price from a scraped one and report it.

    Ordering: cheapest way to end up with enough. For each offer, work out
    how many packs it takes to reach the amount needed and what that costs,
    then sort by that total.

    This is not the same as the best fit. Needing 30 g, a 50 g bottle at $30
    beats a 25 g bottle at $40, even though the 50 g overshoots and the 25 g
    does not even cover it. Overbuying wastes material; buying the wrong pack
    wastes money, and money is what is being minimised here.

    Offers quoted by volume cannot be compared this way and sort last.

    Returns [] when nothing is found. Note that this cannot distinguish
    "nobody sells it" from "the marketplace was unreachable" — use search()
    when that difference matters, which for a purchase decision it usually
    does.
    """
    return search(smiles, grams, name, sources).options


class Result(NamedTuple):
    """
    What a search found, and what it could not reach.

    errors maps a source to why it failed. Empty means every source answered,
    and an empty options list then genuinely means nobody sells this. That
    distinction is the whole reason this type exists.
    """

    options: List[dict]
    errors: Dict[str, str]

    @property
    def complete(self) -> bool:
        """True when every requested source answered."""
        return not self.errors


def search(
    smiles: str,
    grams: float = None,
    name: str = "",
    sources: List[str] = None,
) -> Result:
    """
    find_options, but it also tells you which sources failed.

    Use this when the answer matters: an empty result from a working
    marketplace means nobody sells the compound, and an empty result from a
    marketplace that timed out means nothing at all.
    """
    if not smiles:
        return Result([], {})

    wanted = sources or list(SOURCES)
    options: List[dict] = []
    errors: Dict[str, str] = {}

    for key in wanted:
        module = SOURCES.get(key)
        if module is None:
            errors[key] = "no such source"
            continue

        # A source with no key is skipped, not failed. Not configuring
        # Mcule is a choice; Mcule being down is an incident.
        if not getattr(module, "API_KEY", ""):
            continue

        try:
            found = module.find_options(smiles, grams, name) or []
        except SourceError as e:
            # One marketplace being down must not lose the others' answers,
            # but it must not look like an answer either.
            log.warning("%s failed for %s: %s", key, smiles, e.detail)
            errors[key] = e.detail
            continue
        except Exception as e:
            log.warning("%s raised for %s: %r", key, smiles, e)
            errors[key] = f"{type(e).__name__}: {e}"
            continue

        for option in found:
            option["source"] = key
            options.append(option)

    options.sort(key=lambda o: _total_cost(o, grams))
    return Result(options, errors)


def _total_cost(option: dict, grams: float = None) -> tuple:
    """
    What this offer costs to satisfy the need, as a sort key.

    Packs are indivisible, so needing 30 g of something sold in 25 g bottles
    means buying two of them. The comparison is between total prices paid,
    not between unit prices, because a cheaper price per gram on a pack you
    have to buy three of is not cheaper.

    Returns a tuple so unusable offers sort last rather than crashing the
    run: no price, or a pack quoted by volume when the need is a mass.
    """
    import math

    price = _price(option)
    pack = _grams(option)

    if price is None:
        return (2, float("inf"))
    if grams is None or pack is None or pack <= 0:
        return (1, price)

    packs = max(1, math.ceil(grams / pack))
    return (0, packs * price)


def cheapest(smiles: str, grams: float = None, **kwargs) -> Optional[dict]:
    """The first option find_options would recommend, or None."""
    options = find_options(smiles, grams, **kwargs)
    return options[0] if options else None
