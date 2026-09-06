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
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, NamedTuple, Optional

from . import cache, chemspace, mcule, molport
from .errors import SourceError
from .ranking import grams_of, price_of, total_cost

# Kept under their old private names so existing callers and tests keep
# working. ranking.py is where these actually live now, because the vendor
# modules need them too and cannot import from here.
_grams = grams_of
_price = price_of
_total_cost = total_cost

log = logging.getLogger(__name__)

__version__ = "0.1.0"

SOURCES = {
    "molport": molport,
    "chemspace": chemspace,
    "mcule": mcule,
}



def _purity(option: dict) -> Optional[float]:
    """
    Purity as a number, or None when the supplier does not state one.

    Suppliers write it as "98%", ">=98", "95.5", or leave it out. None means
    unknown, which is not the same as low and must not be treated as either.
    """
    import re

    match = re.search(r"[\d.]+", str(option.get("purity_offered") or ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None



def find_options(
    smiles: str,
    grams: float = None,
    name: str = "",
    sources: List[str] = None,
    min_purity: float = None,
    density: float = None,
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
    return search(smiles, grams, name, sources, min_purity, density).options


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
    min_purity: float = None,
    density: float = None,
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

    # The sources know nothing about each other, so ask them at the same time.
    # Measured per compound: MolPort 10s, ChemSpace 3s, Mcule 66s. Sequentially
    # that is 79 seconds of waiting for 79 seconds of network. In parallel it
    # is however long the slowest one takes.
    #
    # Threads rather than async because every call here is a blocking socket
    # read in the standard library, and three threads is not a concurrency
    # design worth having an event loop for.
    def ask(key):
        module = SOURCES.get(key)
        if module is None:
            return key, None, "no such source"

        # A source with no key is skipped, not failed. Not configuring
        # Mcule is a choice; Mcule being down is an incident.
        if not getattr(module, "API_KEY", ""):
            return key, [], None

        # A cached answer is still an answer, and costs no request. The
        # config string goes into the key because shipping country, category
        # filters and density all change what comes back.
        # Both spellings, because the vendor modules do not agree: chemspace
        # calls it SHIP_TO and molport calls it SHIPPING_COUNTRY. Reading only
        # the first left molport's country out of the key entirely, so a US
        # answer was served for a GB query for seven days.
        ship_to = getattr(module, "SHIP_TO", "") or getattr(
            module, "SHIPPING_COUNTRY", ""
        )
        config = (
            f"{ship_to}:"
            f"{getattr(module, 'CATEGORIES', '')}:{density or ''}"
        )
        found = cache.get(key, smiles, grams, config)
        if found is not None:
            return key, found, None

        try:
            try:
                found = module.find_options(smiles, grams, name, density) or []
            except TypeError:
                # Sources that do not take a density (MolPort and Mcule quote
                # by mass only) keep the three-argument signature.
                found = module.find_options(smiles, grams, name) or []
        except SourceError as e:
            # One marketplace being down must not lose the others' answers,
            # but it must not look like an answer either.
            log.warning("%s failed for %s: %s", key, smiles, e.detail)
            return key, None, e.detail
        except Exception as e:
            log.warning("%s raised for %s: %r", key, smiles, e)
            return key, None, f"{type(e).__name__}: {e}"

        # Only successes are cached. A failure returns above, which is the
        # whole reason those are separate paths.
        cache.put(key, smiles, grams, found, config)
        return key, found, None

    with ThreadPoolExecutor(max_workers=len(wanted) or 1) as pool:
        for key, found, error in pool.map(ask, wanted):
            if error is not None:
                errors[key] = error
                continue
            for option in found:
                option["source"] = key
                options.append(option)

    if min_purity is not None:
        for option in options:
            option["meets_purity"] = _meets_purity(option, min_purity)

    # Four bands, worst failure first. Cost only decides between offers that
    # are equally acceptable, because the cheapest row is not the right answer
    # when it is the wrong chemical, the wrong grade, or a drum.
    options.sort(
        key=lambda o: (
            _match_rank(o),
            _purity_rank(o, min_purity),
            _overbuy_rank(o, grams, density),
            total_cost(o, grams, density),
        )
    )
    return Result(options, errors)


# A pack more than this many times the amount needed is ranked below one that
# fits, however cheap it is. Set from a chemist's judgement rather than from
# arithmetic: at 15 g needed the cheapest way to end up with enough was a 1 kg
# bottle at $14.63, beating 25 g at $27, and a kilogram of an amine on a bench
# for a 15 g reaction is a storage, hazard and shelf-life problem the price
# comparison cannot see.
MAX_OVERBUY = 5.0


def _match_rank(option: dict) -> int:
    """
    0 for the compound that was asked for, 1 for anything else.

    ChemSpace answers a structure search with the structure AND its salts.
    Those are different chemicals and they are systematically cheaper, so they
    have to be banded here too, not only inside the ChemSpace client: this
    sort runs over every source's offers after the fact and would otherwise
    lift a salt straight back to the top.

    Sources that report no match type (MolPort, Mcule) rank 0. Absence of the
    field is not evidence of a mismatch.
    """
    match = str(option.get("match_type") or "").lower()
    return 0 if match in ("exactmatch", "exact", "perfect", "") else 1


def _overbuy_rank(option: dict, grams: float = None, density: float = None) -> int:
    """
    0 for a pack a lab would actually order, 1 for a drum.

    Nothing is dropped: the drum is still listed, and a chemist who wants it
    can take it. It just stops outranking a bottle that fits.

    Unknown either way ranks 0. With no amount needed there is nothing to be
    excessive relative to, and a pack whose size will not convert to grams is
    already sorted last by total_cost.
    """
    if not grams:
        return 0
    pack = grams_of(option, density)
    if pack is None:
        return 0
    return 1 if pack > grams * MAX_OVERBUY else 0


def _meets_purity(option: dict, min_purity: float):
    """True, False, or None when the supplier states no purity."""
    purity = _purity(option)
    return None if purity is None else purity >= min_purity


def _purity_rank(option: dict, min_purity: float = None) -> int:
    """
    Which band an offer falls into when a purity is required.

    0  states a purity that meets the requirement
    1  states no purity at all
    2  states a purity below the requirement

    Offers that fail are ranked last rather than dropped, for the same reason
    an unpriced offer is kept: a chemist deciding whether 95% will do is a
    better outcome than a list that quietly went shorter. An offer with no
    stated purity sits between the two, because unknown is not the same as
    low, and cannot be treated as either.
    """
    if min_purity is None:
        return 0
    meets = _meets_purity(option, min_purity)
    if meets is None:
        return 1
    return 0 if meets else 2



def cheapest(smiles: str, grams: float = None, **kwargs) -> Optional[dict]:
    """The first option find_options would recommend, or None."""
    options = find_options(smiles, grams, **kwargs)
    return options[0] if options else None
