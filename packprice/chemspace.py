"""
ChemSpace: a second marketplace, for the compounds MolPort does not stock.

MolPort answered 5 of the 15 orderable compounds in the benchmark below.
The other 10 fell through to the scraper, which is slow and unreliable. A
second marketplace is the cheapest way to close part of that gap, and the two
catalogues do not overlap completely: ChemSpace carries suppliers MolPort
does not, and quotes in USD and EUR.

WHY NOT ChemPrice. There is a published package (Sorkun et al., Chemistry-
Methods 2025, github.com/bsaliou/ChemPrice) that already wraps MolPort,
ChemSpace and Mcule behind one call. It was the obvious thing to use, so it
got measured against the code here on the five compounds MolPort answers:

    2-fluoropyridine        ours: A2B Chem, 25 g, $10
                       ChemPrice: Angene, 30 mg, $128
    acetic acid             ours: A2B Chem, 100 g, $15
                       ChemPrice: TimTec, 15 mg, $500, back-ordered
    Et3N, Tf2O, 10-undecenoyl chloride
                       ChemPrice: no offer at all

It is not that ChemPrice is bad. It is built for drug discovery, where the
question is what a novel molecule costs at milligram scale, and it asks the
marketplaces exactly that. A synthetic chemist running a published procedure
needs 23.6 mL, and a 30 mg vial is not an answer. Its ChemSpace half also
returns 404 now; the repository has not been committed to in two years.

So the quantity goes INTO the query rather than being filtered out
afterwards, and the categories below exclude screening compounds, which are
the milligram vials that trapped ChemPrice.

TWO-LAYER AUTH. The API key never touches a search. It buys an access token
from /auth/token which expires in about four hours, and the token is what
every search carries. The token is cached in this module for that reason:
one auth call per process, not one per compound.

Rate limit is 40 requests a minute, reported in X-Rate-Limit-Remaining.
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from .errors import SourceError

API_KEY = os.environ.get("CHEMSPACE_API_KEY", "")
BASE = "https://api.chem-space.com"
VERSION = "4.1"

# CSSB is in-stock building blocks, CSMB is make-on-demand building blocks.
#
# Deliberately NOT CSSS or CSMS. Those are screening compounds: catalogues of
# novel molecules sold as 1-20 mg vials for assay plates. They are the right
# answer to "does anyone have this molecule at all" and the wrong answer to
# "I need 26.8 g of TEMPO on Thursday". Including them is the single mistake
# that made ChemPrice quote $500 for 15 mg of acetic acid.
CATEGORIES = "CSSB,CSMB"

# Two-letter ISO. Prices and availability are country-specific, so this is
# not cosmetic: the same bottle can be listed by different suppliers, at
# different prices, depending on where it ships.
#
# US to match molport.py, so the two sources are comparable. Override with
# CHEMSPACE_SHIP_TO when ordering somewhere else.
SHIP_TO = os.environ.get("CHEMSPACE_SHIP_TO", "US")

# ChemSpace lists every pack a vendor sells, so a popular building block can
# come back with dozens of rows. A caller only needs enough to choose from.
MAX_OPTIONS = 12

_token = {"value": "", "expires_at": 0.0}

# What the server last told us about our own quota. Populated from the
# X-Rate-Limit-* headers that come back on every response, including errors.
_quota = {"remaining": None, "reset_at": 0.0}


def _note_quota(headers, now: float = None) -> None:
    """
    Record what the server says is left.

    ChemSpace reports the quota on every response: how many requests remain
    in the current window and how many seconds until it resets. Reading that
    is better than counting requests here, because the server's number is the
    one that decides, and it already accounts for calls made by anything else
    using the same key.
    """
    now = time.time() if now is None else now
    try:
        remaining = headers.get("X-Rate-Limit-Remaining")
        reset = headers.get("X-Rate-Limit-Reset")
    except AttributeError:
        return
    if remaining is not None:
        try:
            _quota["remaining"] = int(remaining)
        except (TypeError, ValueError):
            pass
    if reset is not None:
        try:
            _quota["reset_at"] = now + int(reset)
        except (TypeError, ValueError):
            pass


def _wait_needed(now: float = None) -> float:
    """
    Seconds to wait before the next request, 0 if none.

    Only waits when the server has said there is nothing left. Slowing down
    at 5 remaining would be guessing; the quota is there to be used.
    """
    now = time.time() if now is None else now
    if _quota["remaining"] is None or _quota["remaining"] > 0:
        return 0.0
    return max(0.0, _quota["reset_at"] - now)


def _respect_quota() -> None:
    """Sleep out the rest of the window if the quota is spent."""
    wait = _wait_needed()
    if wait > 0:
        # A whole window is 60 seconds. Waiting it out is slow and correct;
        # hammering a 429 is fast and gets the key throttled harder.
        time.sleep(wait + 0.5)
        _quota["remaining"] = None


def _auth() -> str:
    """Access token, cached until shortly before it expires."""
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]

    req = urllib.request.Request(
        f"{BASE}/auth/token",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    try:
        data = json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise SourceError("chemspace", f"auth failed, HTTP {e.code}")
    except Exception as e:
        raise SourceError("chemspace", f"auth failed, {type(e).__name__}: {e}")

    _token["value"] = data.get("access_token", "")
    # Renew a minute early rather than discovering expiry as a 401 mid-run.
    _token["expires_at"] = time.time() + max(60, data.get("expires_in", 3600) - 60)
    return _token["value"]


def _multipart(fields: dict) -> tuple:
    """
    The search endpoints take multipart/form-data, which urllib will not build.

    Small enough to write out: a boundary, one part per field, a closing
    boundary. Using requests here would mean a dependency for six lines.
    """
    boundary = "----pack-organic-price-boundary"
    body = b""
    for name, value in fields.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def _search_exact(smiles: str) -> dict:
    token = _auth()
    if not token:
        raise SourceError("chemspace", "no access token returned")

    body, content_type = _multipart({"SMILES": smiles})
    url = (
        f"{BASE}/v{VERSION.split('.')[0]}/search/exact"
        f"?shipToCountry={SHIP_TO}&count=25&page=1&categories={CATEGORIES}"
    )
    req = urllib.request.Request(
        url,
        body,
        {
            "Accept": f"application/json; version={VERSION}",
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        },
        method="POST",
    )
    _respect_quota()
    try:
        response = urllib.request.urlopen(req, timeout=90)
        _note_quota(response.headers)
        return json.load(response)
    except urllib.error.HTTPError as e:
        _note_quota(e.headers)

        # A token lasts about four hours, so a long run can outlive one. Drop
        # it and retry once with a fresh one; only give up if that fails too.
        if e.code == 401:
            _token["value"] = ""
            token = _auth()
            req.headers["Authorization"] = f"Bearer {token}"
            try:
                response = urllib.request.urlopen(req, timeout=90)
                _note_quota(response.headers)
                return json.load(response)
            except Exception as retry_error:
                raise SourceError("chemspace", f"after token refresh: {retry_error}")

        # 429 means we asked too fast despite the headers, which happens when
        # something else is using the same key. Wait the window out once, then
        # try again. Only the second failure is reported as an error.
        if e.code == 429:
            reset = e.headers.get("X-Rate-Limit-Reset") if e.headers else None
            try:
                time.sleep(min(65, int(reset) + 0.5))
            except (TypeError, ValueError):
                time.sleep(60)
            _quota["remaining"] = None
            try:
                response = urllib.request.urlopen(req, timeout=90)
                _note_quota(response.headers)
                return json.load(response)
            except Exception:
                raise SourceError(
                    "chemspace", "rate limited twice, 40 requests a minute"
                )

        raise SourceError("chemspace", f"HTTP {e.code}")
    except Exception as e:
        raise SourceError("chemspace", f"{type(e).__name__}: {e}")


def find_options(smiles: str, grams: float = None, name: str = "") -> list:
    """
    One compound, in the same shape molport.find_options returns, so a
    caller can treat every source identically.

    grams is accepted but not sent: ChemSpace has no amount parameter, it
    returns every pack a vendor lists. It is used to sort, so the packs
    closest to what the procedure needs come first and the caller sees the
    useful ones even when the list is truncated.

    Returns [] when ChemSpace has no priced offer, which is a real answer and
    not an error: the caller falls through to the next source.
    """
    if not API_KEY or not smiles:
        return []

    data = _search_exact(smiles)
    items = data.get("items") or []

    options = []
    unpriced = 0
    for item in items:
        for offer in item.get("offers") or []:
            for price in offer.get("prices") or []:
                usd = price.get("priceUsd")
                if usd is None:
                    # Vendor lists the pack but quotes on request. Counted,
                    # not invented: a price we cannot see is not a price.
                    unpriced += 1
                    continue

                notes = [f"via ChemSpace, {item.get('matchType', 'match')}"]
                if offer.get("leadTimeDays"):
                    notes.append(f"{offer['leadTimeDays']} working days")
                if item.get("isDangerousGood"):
                    notes.append("flagged dangerous goods")

                options.append(
                    {
                        "supplier": offer.get("vendorName") or "unknown",
                        "catalog_number": offer.get("vendorCode"),
                        "product_url": item.get("link"),
                        "purity_offered": (
                            f"{offer['purity']}%" if offer.get("purity") else None
                        ),
                        "pack_size_amount": price.get("pack"),
                        "pack_size_unit": price.get("uom"),
                        "min_order_amount": None,
                        "min_order_unit": None,
                        "price": f"${usd}",
                        "needs_phone_call": "no",
                        "notes": ". ".join(notes),
                    }
                )

    if unpriced and options:
        options[0]["notes"] += f". {unpriced} further offers quote on request"

    if grams:
        options.sort(key=lambda o: abs((_in_grams(o) or 0) - grams))

    return options[:MAX_OPTIONS]


def _in_grams(option: dict) -> Optional[float]:
    """Pack size in grams, for sorting only. None when the unit is not a mass."""
    scale = {"g": 1.0, "mg": 0.001, "kg": 1000.0}.get(
        str(option.get("pack_size_unit") or "").lower()
    )
    amount = option.get("pack_size_amount")
    return amount * scale if scale and amount is not None else None
