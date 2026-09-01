"""
packprice — what pack do I buy, and what does it cost.

Chemical marketplaces answer "what does this molecule cost" well. A synthetic
chemist working from a published procedure has a different question: the
paper says 23.6 mL of 10-undecenoyl chloride, so which pack, from whom, and
how much is left in the bottle afterwards.

Those questions look similar and are not. Ask a marketplace the first one and
it will happily quote a 30 mg vial, which is a real price for a quantity
nobody running this reaction can use. So packprice puts the AMOUNT NEEDED
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

from typing import List, Optional

from . import chemspace, molport

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

    Ordering: packs that cover the amount needed come first, smallest such
    pack first, then everything else by price. A 25 g bottle when you need
    7.6 g beats a 5 g bottle you would have to buy twice.

    Returns [] when nothing is found. That is an answer, not an error.
    """
    wanted = sources or list(SOURCES)
    options = []

    for key in wanted:
        module = SOURCES.get(key)
        if module is None:
            continue
        try:
            found = module.find_options(smiles, grams, name) or []
        except Exception:
            # One marketplace being down must not lose the others' answers.
            found = []
        for option in found:
            option["source"] = key
            options.append(option)

    def rank(option):
        pack = _grams(option)
        price = _price(option)
        covers = grams is not None and pack is not None and pack >= grams
        return (
            0 if covers else 1,
            pack if covers else (price if price is not None else float("inf")),
            price if price is not None else float("inf"),
        )

    options.sort(key=rank)
    return options


def cheapest(smiles: str, grams: float = None, **kwargs) -> Optional[dict]:
    """The first option find_options would recommend, or None."""
    options = find_options(smiles, grams, **kwargs)
    return options[0] if options else None
