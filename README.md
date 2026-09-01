# pack-organic-price

Which pack to buy, and what it costs, across chemical marketplaces.

Chemical marketplaces answer *what does this molecule cost* well. A synthetic
chemist working from a published procedure has a different question: the paper
says 23.6 mL of 10-undecenoyl chloride, so which pack, from whom, and how much
is left in the bottle afterwards.

Ask a marketplace the first question and it will quote a 30 mg vial. That is a
real price for a quantity nobody running the reaction can use.

```python
from packprice import find_options

find_options("Fc1ccccn1", grams=7.6)
# [{'supplier': 'A2B Chem LLC', 'pack_size_amount': 25.0, 'pack_size_unit': 'g',
#   'price': '$10', 'source': 'molport', 'purity_offered': '98%', ...}]
```

Results are ranked by the **cheapest way to end up with enough**: how many packs
it takes to reach the amount needed, times the price. Needing 30 g, a 50 g bottle
at $30 beats a 25 g bottle at $40, even though the 50 g overshoots. Overbuying
wastes material; buying the wrong pack wastes money.

## Command line

```bash
pack-price "Fc1ccccn1" --grams 7.6
```

```
SOURCE     SUPPLIER                         PACK     PRICE  PURITY     TOTAL  AGE
---------------------------------------------------------------------------------
chemspace  Angene International Limit       10 g      $4.5     98%      $4.5  live
mcule      Mcule                         7600 mg        $6     98%        $6  live
molport    A2B Chem LLC                     25 g       $10     99%       $10  live
```

`TOTAL` is what you actually pay: the price times the number of packs it takes
to reach the amount needed, shown as `$54 x2` when it is more than one.

```bash
pack-price "CC1(C)CCCC(C)(C)N1[O]" --grams 26.8 --purity 99   # band by purity
pack-price "[Zn]" --grams 16.3 --json                          # raw output
pack-price "CCO" --sources molport,mcule                       # a subset
pack-price --clear-cache
```

Exit status is 1 when a source failed, so a script can tell an incomplete
answer from a complete one.

## Install

```bash
pip install -e .
```

Installs as `pack-organic-price`, imports as `packprice` — the long name for
the package index, the short one for typing. No dependencies beyond the
standard library.

## Purity

A procedure that specifies 99% cannot be run on 90% material, however cheap it
is. Pass the purity the procedure requires and offers are banded accordingly.

```python
find_options("CC1(C)CCCC(C)(C)N1[O]", grams=26.8, min_purity=99)
```

```
meets the requirement   first
states no purity        next
below the requirement   last
```

Nothing is dropped, and each offer carries `meets_purity` as `True`, `False`
or `None`. A chemist deciding whether 95% will do is a better outcome than a
list that quietly went shorter — and "no purity stated" is not the same as
"low purity", so it is neither passed nor failed.

## When it fails

`find_options` returns a list, and an empty list is ambiguous: nobody sells the
compound, or the marketplace was unreachable. Those lead to opposite decisions.
`search` keeps them apart.

```python
from packprice import search

result = search("Fc1ccccn1", grams=7.6)
result.options      # same list find_options returns
result.errors       # {'molport': 'HTTP 401: Invalid API key!'}
result.complete     # False — at least one source did not answer
```

A source with no API key set is skipped silently and is not an error: not
configuring Mcule is a choice, Mcule being down is an incident.

## Keys

Set whichever you have. Sources without a key are skipped silently.

| Variable | Where to get it |
|---|---|
| `MOLPORT_API_KEY` | molport.com |
| `CHEMSPACE_API_KEY` | info@chem-space.com |
| `MCULE_API_KEY` | mcule.com/accounts/api-access/ |

`CHEMSPACE_SHIP_TO` sets the delivery country as a two-letter code, default `US`.
Prices and availability are country-specific.

## Caching

Answers are cached to disk for **seven days**. Asking the same question twice
costs one request, not two.

Seven days is a judgement, not a technical fact, so here is the reasoning. A
chemist grading these results scored a price quoted today as 5 out of 5, a
month old as 4, two months old as 3. Seven days sits comfortably inside
"today" while still absorbing the repeated runs of a working session.

```bash
PACKPRICE_CACHE_DAYS=30    # keep prices for a month
PACKPRICE_CACHE_DAYS=0     # no cache at all
PACKPRICE_CACHE_DIR=...    # default ~/.cache/pack-organic-price
```

Failures are never cached — a timeout is not an answer. An honest empty
result is, because "no supplier sells this" is a real finding, and the expiry
is what stops it being true forever.

Each cached option carries `retrieved_at`, so a caller can show the age
rather than implying the price is live. `cache.age_days(option)` returns it,
or `None` when the price came back live.

## Rate limits

ChemSpace allows 40 requests a minute and reports the remaining budget in
headers on every response, errors included. The client reads those rather
than counting its own calls, because the server's number is the one that
decides and it already accounts for anything else using the same key.

It waits only when the server says nothing is left, then waits out the rest
of the window. A 429 that slips through anyway is retried once after the
window closes; only a second failure is reported as an error.

## Tests

```bash
python -m unittest discover -s tests
```

No network, no keys, milliseconds. They run on every push against Python 3.9,
3.11 and 3.13.

That the suite needs no credentials is deliberate: a test that required API
keys could not run on a fork, would fail whenever a marketplace had an
outage, and would end up skipped until nobody trusted it. What the suite does
not cover — whether the marketplaces still answer the way this code expects —
is what [BENCHMARK.md](BENCHMARK.md) is for, and that is run by hand.

Everything tested here is the arithmetic: price parsing, pack conversion,
ranking, purity banding, the cache and the rate limiter, and whether a source
failed or honestly found nothing.

## Coverage

Measured by hand against the fifteen orderable compounds of
*Org. Synth.* **2023**, *100*, 136.

| Source | Answered | Cheapest on | Mean seconds |
|---|---|---|---|
| ChemSpace | 15 / 15 | 12 | 3.1 |
| Mcule | 8 / 15 | 1 | 66.1 |
| MolPort | 5 / 15 | 2 | 10.2 |

None is a superset of the others, so ask all three — but ChemSpace answered
everything and was usually cheapest, and Mcule is twenty times slower than
the other two.

Full table, method and caveats in [BENCHMARK.md](BENCHMARK.md).

Mcule works differently: it prices a quantity rather than listing bottles, so
asking for 7.6 g returns a quote for 7.6 g. That removes overbuying entirely
when it has the compound. Its amounts are in milligrams, and its defaults are
1 mg to 10 mg, which is a reminder of who it is built for — the amount needed
is sent as-is rather than rounded down to something it is likely to stock.

## What this is not

Bulk solvents and prepared solutions are not marketplace products. Ask for
dichloromethane and you are offered a 1 g vial, because building-block
catalogues do not stock 2.5 L Winchesters. Ask for `1 M HCl` and you get the
gas. Filter those out first, or accept that a chemist has to read the answer.

Prices are what the marketplace reports at query time. Nothing here is
invented, and a source with no price returns nothing rather than a guess.

## Prior art

[ChemPrice](https://github.com/bsaliou/ChemPrice) (Sorkun et al.,
*Chemistry–Methods* 2025, BSD-3) had the idea of one interface over these
marketplaces first, and this package would not exist without having read it.
It targets drug discovery, quotes at milligram scale, and its ChemSpace
endpoint has returned 404 since the last commit two years ago.

## Releasing

See [RELEASING.md](RELEASING.md). Not published to PyPI yet — install from
source with `pip install -e .`.

## Licence

BSD-3-Clause.
