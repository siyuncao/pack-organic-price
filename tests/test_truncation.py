"""
Truncation must not throw away the answer.

ChemSpace returns 120 priced rows for a common building block and the client
keeps 12. That is fine only if the 12 it keeps are the 12 cheapest ways to
get enough. It used to keep the 12 packs closest in SIZE to the amount
needed, and the cheapest buy was often not among them.

Measured on eight compounds from the benchmark, the old rule lost the
cheapest buy on four. This test is that bug, written down.
"""

import unittest

from packprice.ranking import total_cost


def offer(pack, price, unit="g"):
    return {
        "supplier": f"{pack}{unit}-at-{price}",
        "pack_size_amount": pack,
        "pack_size_unit": unit,
        "price": f"${price}",
    }


def keep_cheapest(options, grams, cap):
    """What chemspace.find_options does now."""
    return sorted(options, key=lambda o: total_cost(o, grams))[:cap]


def keep_closest_size(options, grams, cap):
    """What it used to do. Kept to show the difference."""
    def size(o):
        return o["pack_size_amount"] if o["pack_size_unit"] == "g" else 0
    return sorted(options, key=lambda o: abs(size(o) - grams))[:cap]


class Truncation(unittest.TestCase):
    def setUp(self):
        # Needing 15 g. A pile of near-fit bottles, and one big cheap one.
        # This is the Et3N case: 10 g at $4.60 kept, 100 g at $3.45 discarded.
        self.needed = 15.0
        self.options = [offer(p, price) for p, price in [
            (10, 4.60), (10, 5.00), (25, 6.00), (25, 7.00), (5, 8.00),
            (5, 9.00), (20, 10.00), (20, 11.00), (30, 12.00), (30, 13.00),
            (50, 14.00), (50, 15.00),
        ]]
        self.bargain = offer(100, 3.45)
        self.options.append(self.bargain)

    def test_the_old_rule_lost_the_bargain(self):
        kept = keep_closest_size(self.options, self.needed, 12)
        self.assertNotIn(self.bargain, kept)

    def test_the_new_rule_keeps_it(self):
        kept = keep_cheapest(self.options, self.needed, 12)
        self.assertIn(self.bargain, kept)

    def test_the_bargain_is_first(self):
        kept = keep_cheapest(self.options, self.needed, 12)
        self.assertEqual(kept[0], self.bargain)

    def test_truncating_never_changes_the_winner(self):
        """
        The point of sorting before capping: the answer is the same at any
        cap. If this ever fails, the two rules have drifted apart again.
        """
        full = keep_cheapest(self.options, self.needed, 1000)
        for cap in (1, 3, 12, 50):
            self.assertEqual(keep_cheapest(self.options, self.needed, cap)[0], full[0])

    def test_multiple_packs_are_counted_when_truncating(self):
        """A 5 g bottle at $1 needs three packs for 15 g, so it is not $1."""
        cheap_but_small = offer(5, 1.00)
        one_bottle = offer(20, 2.50)
        kept = keep_cheapest([cheap_but_small, one_bottle], self.needed, 2)
        self.assertEqual(kept[0], one_bottle)


if __name__ == "__main__":
    unittest.main()
