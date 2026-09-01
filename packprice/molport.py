"""
MolPort: supplier data without scraping.

A marketplace API covering 80+ suppliers. You send a SMILES and an amount and
get back a real offer: supplier, pack size, price, purity, hazard flag,
delivery days. No fetching, no rendering, no extraction, so none of the three
failure modes of scraping a supplier website can happen here.

Measured against pages verified by hand, it is both cheaper and more honest
than the scraper:

    2-fluoropyridine   MolPort $10 / 25 g     Sigma $41.50 / 10 g
    Tf2O               MolPort $41 / 25 g     TCI   $94.00 / 25 g

It also knows when a product is DISCONTINUED, which is the one failure the
scraper cannot detect and the one that matters most: it invented a price for a
dead Fisher catalogue number, and a chemist would have ordered it.

WHAT IT DOES NOT COVER. MolPort's suppliers are building-block houses
(Enamine, Combi-Blocks, A2B Chem, AK Scientific), not bulk distributors.
Commodity chemicals come back as "discontinued, 0 offers from 0 suppliers":

    found:      Tf2O, 4-bromoanisole, triethylamine, 2-fluoropyridine,
                10-undecenoyl chloride, acetic acid
    not found:  TEMPO, zinc dust, dichloromethane

Checked on their website: those are in the database with the right CAS, just
with no active supplier offer. So "not found" here is TRUE, not a bug, and
that is why the scraper stays as a fallback.
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from .errors import SourceError

API_KEY = os.environ.get("MOLPORT_API_KEY", "")
BASE = "https://api.molport.com/v1"

# MolPort quotes by mass only. Volumes have to be converted first.
MEASURE = "g"


def _call(method: str, path: str, body: dict = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        json.dumps(body).encode() if body else None,
        {"X-API-Key": API_KEY, "Content-Type": "application/json"},
        method=method,
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        body = e.read()[:200].decode("utf8", "replace")
        raise SourceError("molport", f"HTTP {e.code}: {body}")
    except Exception as e:
        raise SourceError("molport", f"{type(e).__name__}: {e}")


def _parse_unit(unit: str):
    """'25 g' -> (25.0, 'g'). MolPort returns the pack as one string."""
    if not unit:
        return None, None
    parts = str(unit).split()
    try:
        return float(parts[0]), (parts[1] if len(parts) > 1 else None)
    except (ValueError, IndexError):
        return None, None


def find_options(smiles: str, grams: float, name: str = "") -> list:
    """
    One compound, one quote request, in this package's option shape.

    Returns [] when MolPort has no offer. That is a real answer, not a
    failure: it means no supplier in their network currently sells it, and
    the caller should fall back to the scraper.
    """
    if not API_KEY or not smiles or not grams:
        return []

    # amount must be an integer, and asking for less than 1 g of anything is
    # below the smallest pack any supplier lists.
    amount = max(1, round(grams))

    sub = _call(
        "POST",
        "/list-searches",
        {
            "search_items_type": "smiles",
            "search_items": [smiles],
            "amount": amount,
            "min_amount": 1,
            "measure": MEASURE,
            "shipping_country": "US",
            # perfect/exact first, 'any' last, so a loose structural match is
            # only used when nothing better exists.
            "match_types": ["perfect", "exact", "racemate", "any"],
            "selection_method": "lowest price",
            "shipping_method": "direct",
            "search_name": name[:40] or "pack-organic-price",
        },
    )
    key = sub.get("search_key")
    if not key:
        # A 200 with no search key means MolPort understood the request and
        # declined it. Its own message is more useful than a bare [].
        raise SourceError("molport", sub.get("message") or "no search key returned")

    # Processing is asynchronous, so poll. It normally finishes in seconds.
    for _ in range(20):
        if _call("GET", f"/list-searches/status/{key}").get("status") == "finished":
            break
        time.sleep(3)
    else:
        raise SourceError("molport", "search did not finish within 60 seconds")

    data = _call("GET", f"/list-searches/{key}")
    rows = (data.get("request") or {}).get("results") or []

    options = []
    for r in rows:
        if r.get("status") != "found":
            continue
        pack_amount, pack_unit = _parse_unit(r.get("unit"))
        price = r.get("unit_price")

        notes = [f"via MolPort, match {r.get('match_type')}"]
        if r.get("delivery_days"):
            notes.append(f"{r['delivery_days']} working days")
        if r.get("hazardous"):
            notes.append("flagged hazardous by supplier")
        if r.get("controlled"):
            notes.append("CONTROLLED SUBSTANCE")

        options.append(
            {
                "supplier": r.get("supplier_name") or "unknown",
                "catalog_number": r.get("product_id") or r.get("molport_id"),
                "product_url": (
                    f"https://www.molport.com/shop/molecule-link/{r['molport_id']}"
                    if r.get("molport_id")
                    else None
                ),
                "purity_offered": f"{r['purity']}%" if r.get("purity") else None,
                "pack_size_amount": pack_amount,
                "pack_size_unit": pack_unit,
                "min_order_amount": None,
                "min_order_unit": None,
                "price": f"${price}" if price is not None else None,
                # An offer returned by the API is orderable through the API.
                # That is the definition of not needing a phone call.
                "needs_phone_call": "no",
                "notes": ". ".join(notes),
            }
        )

    return options
