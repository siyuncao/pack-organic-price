# packprice

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

## Install

```bash
pip install -e .
```

No dependencies beyond the standard library.

## Keys

Set whichever you have. Sources without a key are skipped silently.

| Variable | Where to get it |
|---|---|
| `MOLPORT_API_KEY` | molport.com |
| `CHEMSPACE_API_KEY` | info@chem-space.com |
| `MCULE_API_KEY` | mcule.com (not yet implemented) |

`CHEMSPACE_SHIP_TO` sets the delivery country as a two-letter code, default `US`.
Prices and availability are country-specific.

## Coverage

Measured by hand against the fifteen orderable compounds of
*Org. Synth.* **2023**, *100*, 136.

| Source | Answered | Notes |
|---|---|---|
| MolPort | 5 / 15 | Best price on four of the five it answered |
| ChemSpace | 15 / 15 | Includes TEMPO and zinc dust, which MolPort lists as discontinued |

Neither is a superset of the other. Ask both.

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

## Licence

BSD-3-Clause.
