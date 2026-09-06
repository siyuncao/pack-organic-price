# Benchmark

How many of a real paper's reagents can each marketplace price, which is
cheapest, and what it actually costs to get the amount the procedure needs.

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
3. Get a SMILES, a density and the total amount needed for each, summing
   repeated uses.
4. Ask each marketplace for that compound at that amount, one source at a
   time, with the disk cache cleared.
5. Record whether it answered, the cheapest offer, and how long it took.

A source counts as answering only if it returned at least one priced offer.
Returning the compound with no price is not an answer to "what does this cost".

**Run it without an HTTP proxy in the way.** Two earlier runs of this
benchmark were corrupted by a local proxy mangling TLS, which showed up as
`SSL: WRONG_VERSION_NUMBER` and would have been recorded as a coverage
collapse if the client did not distinguish a failure from an empty result.

## Results

| Compound | Needed | MolPort | ChemSpace | Mcule |
|---|---|---|---|---|
| pyrrolidine | 7.11 g | — | $21 / 100 ml | $66 / 7110 mg |
| Et3N | 21.0 mL | $57 / 50 g +$45 ship | $3.45 / 100 g | $20 / 15246 mg |
| Anhydrous dichloromethane | 100.0 mL | — | $13.2 / 100 ml | — |
| 10-undecenoyl chloride | 23.6 mL | $34 / 25 g +$40 ship | $13.8 / 25 g | $38 / 22184 mg |
| 1 M HCl | 350.0 mL | — | $3.45 / 100 g | $163 / 1 mg |
| saturated aqueous NaHCO3 | 370.0 mL | — | $3.45 / 25 g | — |
| TEMPO | 26.8 g | — | $36 / 50 g | — |
| 2-fluoropyridine | 6.7 mL | $10 / 25 g +$45 ship | $4.5 / 10 g | $6 / 7571 mg |
| Trifluoromethanesulfonic anhydride | 14.4 mL | $41 / 25 g +$43 ship | $42 / 50 g | $54 / 24149 mg |
| magnesium monoperoxyphthalate hexahydrate | 30.9 g | — | $5.39 / 5 g | — |
| saturated aqueous solution of Na2SO3 | 150.0 mL | — | $4.5 / 10 g | — |
| saturated aqueous Na2CO3 | 300.0 mL | — | $3.45 / 25 g | — |
| acetic acid | 50.0 mL | $15 / 100 g +$45 ship | $3.45 / 100 g | $20 / 52450 mg |
| zinc dust | 16.3 g | — | $12.1 / 50 g | $5 / 16300 mg |
| half-saturated sodium potassium tartrate s | 200.0 mL | — | $3.45 / 25 g | $20 / 1 mg |

Cheapest offer each source returned for the amount asked for, in USD, shipping
to the US, measured on 6 September 2026. MolPort is the only source that
reports a delivery cost; the others do not expose one at all.

## Coverage

| Source | Answered | Mean seconds |
|---|---|---|
| ChemSpace | 15 / 15 | 2.4 |
| Mcule | 9 / 15 | 2.0 |
| MolPort | 5 / 15 | 11.2 |

**ChemSpace answered everything and was cheapest on almost all of it.** If
only one source could be kept, it would be that one.

**MolPort is not redundant**, but it is close. It was cheapest on one
compound, it is the slowest, and it returns a single offer where its own
website lists 73 from 21 suppliers. List Search is a procurement endpoint that
picks for you; the endpoint that lists every offer is refused on a Basic key,
and `/availability-searches` returns "in stock" and nothing else. Its full
catalogue is in the Professional FTP dump, not this API.

**Mcule quotes a minimum order price, not a per-quantity one.** Asking for
16.3 g of zinc dust returns $5, and asking for 1 mg returns the same $5. The
price is flat to roughly 10 g and only moves above it:

    2-fluoropyridine, Mcule
        1 mg      $6    98%   14 working days
      100 mg      $6
     7,600 mg     $6
    100,000 mg   $25    99%   22 working days   (a different supplier)

So its quotes are real, but they are GET QUOTE estimates with a two week lead
time rather than stock on a shelf. It was cheapest on one compound, zinc dust.

## What one hand-check found

The 2-fluoropyridine row was verified against all three websites by hand. It
was correct — Angene 10 g at $4.50 is on the ChemSpace page and is genuinely
the cheapest way to buy 7.6 g there. Checking it surfaced four defects
anyway, three of them real:

| Found | Outcome |
|---|---|
| ChemSpace returns 120 priced rows; the client kept the 12 closest in SIZE, then ranked by COST | fixed |
| Bottles quoted in mL could never win against ones quoted in g | fixed |
| MolPort's `+$45 shipping` was in the response and discarded | now reported |
| "Mcule prices the exact amount you ask for" | wrong, corrected |

Fixing the first two changed the recommendation on **9 of 15** compounds, and
never for the worse:

| Compound | Before | After |
|---|---|---|
| Anhydrous dichloromethane | $10,773.00 | $13.20 |
| Et3N | $9.20 | $3.45 |
| saturated aqueous NaHCO3 | $12.65 | $3.45 |
| acetic acid | $15.00 | $3.45 |
| 1 M HCl | $10.35 | $3.45 |

Dichloromethane is the case worth understanding. Needing 132.5 g, the only
offer the ranking could compare was a 1 g vial at $81 — so 133 of them,
$10,773. A 100 mL bottle at $13.20 was in the same response and invisible,
because millilitres cannot be compared with grams without a density.

Whole basket, all fifteen compounds: **$11,019.88 before, $197.43 after.**
Excluding dichloromethane, $246.88 to $184.23.

One compound, checked by hand, was worth more than a 76-test suite that
passed throughout.

## Shipping

Only MolPort reports it, and it is large: their website shows $33 to $170 per
supplier, so a $10 bottle can be a $55 order. It is carried on each offer as
`shipping_usd` and shown by the CLI, but it is **not** added into the ranking.
Shipping is charged per shipment rather than per compound, and the two sources
that do not report it would look artificially cheap beside the one that does.

**A comparison across sources is therefore not a comparison of what you will
pay.** That is a limit of what these APIs expose.

## What no marketplace can fix

Five of the fifteen are not products:

    1 M HCl · saturated aqueous NaHCO3 · saturated aqueous Na2SO3
    saturated aqueous Na2CO3 · half-saturated sodium potassium tartrate

These are solutions a chemist makes from bench stock. Every quote returned for
them is for the solid salt, which may well be what you want to buy, but is not
what the row asked for. The compound list should not contain them.

## Repeating this

```bash
pack-price --clear-cache
pack-price "<smiles>" --grams <amount> --density <g/mL> --sources chemspace
```

Clear the cache first, or the second run measures this package rather than
the marketplaces. Prices move; the coverage counts are more durable than the
prices, because a catalogue changes far more slowly than a quote.
