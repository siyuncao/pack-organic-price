"""
Purity, which a price-only ranking ignores entirely.

A procedure that specifies 99% cannot be run on 90% material, however cheap
it is. Before this, the cheapest offer won regardless, and a chemist reading
the top row had no way to tell.

The rule: offers that meet the stated purity come first, offers that state no
purity come next, offers below it come last. Nothing is dropped. A chemist
deciding whether 95% will do is a better outcome than a list that quietly
went shorter.
"""

import unittest

from packprice import _meets_purity, _purity, _purity_rank


def offer(purity, price="$10", pack=25):
    return {
        "supplier": "test",
        "purity_offered": purity,
        "price": price,
        "pack_size_amount": pack,
        "pack_size_unit": "g",
    }


class PurityParsing(unittest.TestCase):
    def test_percent_sign(self):
        self.assertEqual(_purity(offer("98%")), 98.0)

    def test_bare_number(self):
        self.assertEqual(_purity(offer("95")), 95.0)

    def test_greater_or_equal(self):
        self.assertEqual(_purity(offer(">=98")), 98.0)

    def test_decimal(self):
        self.assertEqual(_purity(offer("99.5%")), 99.5)

    def test_absent(self):
        self.assertIsNone(_purity(offer(None)))

    def test_unparseable(self):
        self.assertIsNone(_purity(offer("technical grade")))


class MeetsRequirement(unittest.TestCase):
    def test_above(self):
        self.assertTrue(_meets_purity(offer("99%"), 98))

    def test_exactly_at_the_line(self):
        """98% material satisfies a 98% requirement."""
        self.assertTrue(_meets_purity(offer("98%"), 98))

    def test_below(self):
        self.assertFalse(_meets_purity(offer("90%"), 98))

    def test_unknown_is_neither(self):
        """None, not False. Unknown purity is not the same as low purity."""
        self.assertIsNone(_meets_purity(offer(None), 98))


class Ranking(unittest.TestCase):
    def test_no_requirement_means_no_reordering(self):
        """Asking for nothing must not change the price ordering."""
        self.assertEqual(_purity_rank(offer("50%"), None), 0)
        self.assertEqual(_purity_rank(offer(None), None), 0)

    def test_three_bands(self):
        self.assertEqual(_purity_rank(offer("99%"), 98), 0)
        self.assertEqual(_purity_rank(offer(None), 98), 1)
        self.assertEqual(_purity_rank(offer("90%"), 98), 2)

    def test_cheap_and_impure_loses_to_dear_and_pure(self):
        """
        The case this exists for. Half the price, wrong material.
        """
        cheap_impure = offer("90%", price="$25")
        dear_pure = offer("99%", price="$40")
        ordered = sorted([cheap_impure, dear_pure], key=lambda o: _purity_rank(o, 98))
        self.assertEqual(ordered[0]["purity_offered"], "99%")

    def test_unknown_sits_between(self):
        ordered = sorted(
            [offer("90%"), offer(None), offer("99%")],
            key=lambda o: _purity_rank(o, 98),
        )
        self.assertEqual(
            [o["purity_offered"] for o in ordered], ["99%", None, "90%"]
        )

    def test_nothing_is_dropped(self):
        offers = [offer("90%"), offer(None), offer("99%")]
        ordered = sorted(offers, key=lambda o: _purity_rank(o, 98))
        self.assertEqual(len(ordered), 3)


if __name__ == "__main__":
    unittest.main()
