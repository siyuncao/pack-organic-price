"""
Mcule: a third marketplace, and the one that most clearly is not built for this.

Mcule is a drug discovery platform. Its price endpoint takes amounts in
MILLIGRAMS and defaults to quoting 1 mg, 5 mg and 10 mg. That is the right
question for someone screening a novel molecule against a target, and the
wrong one for someone who needs 26.8 g of TEMPO for a published procedure.

It is included anyway, for one reason: coverage is not a matter of opinion.
MolPort answered 5 of 15 orderable compounds in the benchmark and ChemSpace
answered the other 10. Whether Mcule adds anything on top is a question with
an answer, and the only way to get it is to ask.

The amount needed is converted to milligrams and sent as-is rather than being
rounded down to something Mcule is likely to have. A quote for 26,800 mg or
nothing at all is an honest answer. A quote for 10 mg dressed up as an answer
to a 26.8 g question is the mistake this whole package exists to avoid.

TWO REQUESTS PER COMPOUND. Mcule identifies compounds by its own IDs, so a
SMILES has to be looked up first and priced second. The rate limit is 20 a
minute and 200 an hour for an authenticated key, so a fifteen-compound paper
is 30 requests: fine once, and the reason the disk cache exists.

    MCULE_API_KEY   from mcule.com/accounts/api-access/
"""

import json
import os
import urllib.error
import urllib.request

from .errors import SourceError

API_KEY = os.environ.get("MCULE_API_KEY", "")
BASE = "https://mcule.com/api/v1"

# Mcule quotes by mass, in milligrams, and nothing else.
MEASURE = "mg"


def _call(method: str, path: str, body: dict = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        json.dumps(body).encode() if body else None,
        {
            "Authorization": f"Token {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry = e.headers.get("Retry-After") if e.headers else None
            raise SourceError(
                "mcule",
                f"rate limited, retry after {retry or 'unknown'} seconds",
            )
        body_text = e.read()[:200].decode("utf8", "replace")
        raise SourceError("mcule", f"HTTP {e.code}: {body_text}")
    except Exception as e:
        raise SourceError("mcule", f"{type(e).__name__}: {e}")


def _lookup(smiles: str):
    """SMILES to Mcule ID, or None if they do not have the compound."""
    data = _call("POST", "/search/exact/", {"queries": [smiles]})
    for row in data.get("results") or []:
        if row.get("mcule_id"):
            return row["mcule_id"], row.get("url")
    return None, None


def find_options(smiles: str, grams: float = None, name: str = "") -> list:
    """
    One compound, in the shape the other sources return.

    Returns [] when Mcule does not have the compound, or has it but will not
    quote the amount asked for. Both are real answers.
    """
    if not API_KEY or not smiles:
        return []

    mcule_id, url = _lookup(smiles)
    if not mcule_id:
        return []

    # Mcule prices a specific amount rather than listing packs, so the amount
    # needed IS the query. With no amount given, fall back to their default
    # of 1 mg, which at least reveals whether they carry it at all.
    milligrams = max(1, int(round((grams or 0.001) * 1000)))
    data = _call("GET", f"/compound/{mcule_id}/prices/?amounts={milligrams}")

    options = []
    for price in data.get("best_prices") or []:
        if price.get("price") is None:
            continue

        notes = ["via Mcule"]
        if price.get("delivery_time_working_days"):
            notes.append(f"{price['delivery_time_working_days']} working days")

        options.append(
            {
                "supplier": "Mcule",
                "catalog_number": mcule_id,
                "product_url": url or f"https://mcule.com/{mcule_id}/",
                "purity_offered": (
                    f"{price['purity']}%" if price.get("purity") else None
                ),
                "pack_size_amount": price.get("amount"),
                "pack_size_unit": price.get("unit") or MEASURE,
                "min_order_amount": None,
                "min_order_unit": None,
                "price": f"${price['price']}",
                "needs_phone_call": "no",
                "notes": ". ".join(notes),
            }
        )

    return options
