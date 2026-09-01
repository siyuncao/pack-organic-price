# Benchmark

How many of a real paper's reagents can each marketplace actually price, and
which one is cheapest when more than one can.

## The question

Coverage claims are easy to make and easy to get wrong, so this is measured
rather than asserted. The test is not "does this marketplace have the
molecule" — nearly all of them have nearly everything, at some scale. It is
"can it quote the amount a published procedure actually calls for".

## Method, so it can be repeated

1. Take the experimental section of *Org. Synth.* **2023**, *100*, 136, a
   four-step preparation with a published, checked procedure.
2. List every chemical it says to use, and decide for each whether a lab would
   buy it for this experiment or already has it on the shelf. Bulk solvents,
   drying agents and chromatography silica are stock; reagents are not. That
   left **15 orderable compounds**.
3. Get a SMILES and the total amount needed for each, summing repeated uses.
4. Ask each marketplace for that compound at that amount, one source at a
   time, with the disk cache cleared.
5. Record whether it answered, what the cheapest offer was, and how long it
   took.

A source is counted as answering only if it returned at least one priced
offer. Returning the compound with no price is not an answer to "what does
this cost".

## Results


| Compound | Needed | MolPort | ChemSpace | Mcule |
|---|---|---|---|---|
| pyrrolidine | 7.11 g | — | $14.3 / 5 g | $66 / 7110 mg |
| Et3N | 21.0 mL | $57 / 50 g | $4.6 / 10 g | $20 / 15246 mg |
| Anhydrous dichloromethane | 100.0 mL | — | $81 / 1 g | — |
| 10-undecenoyl chloride | 23.6 mL | $34 / 25 g | $13.8 / 25 g | $38 / 22184 mg |
| 1 M HCl | 350.0 mL | — | $10.35 / 25 g | $163 / 1 mg |
| saturated aqueous NaHCO3 | 370.0 mL | — | $12.65 / 50 g | — |
| TEMPO | 26.8 g | — | $36 / 50 g | — |
| 2-fluoropyridine | 6.7 mL | $10 / 25 g | $4.5 / 10 g | $6 / 7600 mg |
| Trifluoromethanesulfonic anhydride | 14.4 mL | $41 / 25 g | $43.89 / 25 g | $54 / 24149 mg |
| magnesium monoperoxyphthalate hexahydrate | 30.9 g | — | $5.39 / 5 g | — |
| saturated aqueous solution of Na2SO3 | 150.0 mL | — | $13.8 / 5 g | — |
| saturated aqueous Na2CO3 | 300.0 mL | — | $12.65 / 100 g | — |
| acetic acid | 50.0 mL | $15 / 100 g | $15.4 / 50 g | $20 / 52450 mg |
| zinc dust | 16.3 g | — | $17 / 25 g | $5 / 16300 mg |
| half-saturated sodium potassium tartrate s | 200.0 mL | — | $6.6 / 25 mg | error |

Prices are the cheapest offer each source returned for the amount asked for,
in USD, shipping to the US, measured on 1 September 2026.

## Coverage

| Source | Answered | Cheapest on | Mean seconds |
|---|---|---|---|
| ChemSpace | 15 / 15 | 12 | 3.1 |
| Mcule | 8 / 15 | 1 | 66.1 |
| MolPort | 5 / 15 | 2 | 10.2 |

**ChemSpace answered everything and was usually cheapest.** If only one source
could be kept, it would be that one.

**MolPort is not redundant.** It was cheapest on two compounds ChemSpace also
had, and its catalogue overlaps rather than nests.

**Mcule prices quantities, not packs.** Ask it for 16.3 g of zinc dust and it
quotes 16,300 mg — $5, against ChemSpace's $17 for a 25 g bottle. When it has
a compound at the amount wanted, nothing is left over. It only had 8 of 15,
and it is by far the slowest.

**Mcule's 66 seconds per compound** is a real cost. It needs two requests, a
SMILES lookup and then a price, and the price call is slow. For a fifteen
compound paper that is sixteen minutes against ChemSpace's forty-five seconds.
This is the main argument for the seven-day cache.

One request failed outright: Mcule dropped the connection on the tartrate
query. It is reported as an error rather than an empty result, which is the
distinction the whole package is built around.

## What the failures have in common

Five of the fifteen are not products at all:

    1 M HCl · saturated aqueous NaHCO3 · saturated aqueous Na2SO3
    saturated aqueous Na2CO3 · half-saturated sodium potassium tartrate

These are solutions a chemist makes from bench stock, so no amount in grams
can be computed for them and no marketplace stocks them as such. Every quote
returned for these rows is for the solid salt, which may be what you want to
buy, but is not what the row asked for. **A marketplace cannot fix this; the
compound list should not contain them.**

The same applies to bulk solvents. Dichloromethane came back as a 1 g vial at
$81 for a procedure needing 132 g, because building-block catalogues do not
stock 2.5 L Winchesters. Ask for a commodity solvent and you get a research
sample.

## Repeating this

```bash
pack-price "<smiles>" --grams <amount> --sources molport
pack-price "<smiles>" --grams <amount> --sources chemspace
pack-price "<smiles>" --grams <amount> --sources mcule
```

Clear the cache first (`pack-price --clear-cache`), or the second run measures
this package rather than the marketplaces.

Prices move. The numbers above are a snapshot, and the coverage counts are
more durable than the prices — a catalogue changes far more slowly than a
quote.
