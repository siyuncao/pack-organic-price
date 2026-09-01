"""
The arithmetic, tested without touching the network.

Everything here is pure: given these offers and this amount needed, what
order should they come out in. No API keys, no requests, so these run in
milliseconds and cannot fail because a marketplace is having a bad day.

The cases are the ones that actually went wrong, or that encode a decision
someone might otherwise "tidy up" later without realising it was deliberate.
"""

import unittest

import packprice
from packprice import _grams, _price, _total_cost, search


def offer(supplier, pack, unit, price, source="test"):
    return {
        "supplier": supplier,
        "pack_size_amount": pack,
        "pack_size_unit": unit,
        "price": price,
        "source": source,
    }


class FakeSource:
    """A marketplace that returns whatever the test tells it to."""

    API_KEY = "set"

    def __init__(self, options=None, raises=None):
        self._options = options or []
        self._raises = raises

    def find_options(self, smiles, grams=None, name=""):
        if self._raises:
            raise self._raises
        return [dict(o) for o in self._options]


class PriceParsing(unittest.TestCase):
    """
    Suppliers write prices in prose. All of these came off real pages.
    """

    def test_plain(self):
        self.assertEqual(_price({"price": "$10"}), 10.0)

    def test_decimal(self):
        self.assertEqual(_price({"price": "$84.85"}), 84.85)

    def test_trailing_words(self):
        # Fisher writes this. It is also the price that turned out to be for
        # a discontinued product, which is why it is in the test suite.
        self.assertEqual(_price({"price": "$84.85 / Each of 1"}), 84.85)

    def test_currency_prefix(self):
        self.assertEqual(_price({"price": "USD 56.60"}), 56.60)

    def test_thousands_separator(self):
        self.assertEqual(_price({"price": "$1,299.00"}), 1299.0)

    def test_missing(self):
        self.assertIsNone(_price({"price": None}))

    def test_unparseable(self):
        self.assertIsNone(_price({"price": "call for quote"}))


class PackSizes(unittest.TestCase):
    def test_grams(self):
        self.assertEqual(_grams(offer("x", 25, "g", "$1")), 25.0)

    def test_milligrams(self):
        self.assertEqual(_grams(offer("x", 500, "mg", "$1")), 0.5)

    def test_kilograms(self):
        self.assertEqual(_grams(offer("x", 1, "kg", "$1")), 1000.0)

    def test_volume_is_not_a_mass(self):
        # A 500 mL bottle cannot be compared with a 25 g bottle without a
        # density, which this package does not have. None, not a guess.
        self.assertIsNone(_grams(offer("x", 500, "mL", "$1")))


class Ranking(unittest.TestCase):
    def order(self, options, grams):
        return [o["supplier"] for o in sorted(options, key=lambda o: _total_cost(o, grams))]

    def test_cheapest_total_wins_over_cheapest_price(self):
        """
        The case that made this rule. Needing 26.8 g of TEMPO:

            Enamine 50 g at $36   ->  one bottle, $36
            Enamine 25 g at $27   ->  two bottles, $54

        $27 is the lower price and the worse buy.
        """
        options = [
            offer("25g-bottle", 25, "g", "$27"),
            offer("50g-bottle", 50, "g", "$36"),
        ]
        self.assertEqual(self.order(options, 26.8), ["50g-bottle", "25g-bottle"])

    def test_overshooting_is_fine_when_it_is_cheaper(self):
        """Buying more than needed is not a fault if it costs less."""
        options = [
            offer("exact-fit", 30, "g", "$40"),
            offer("overshoot", 100, "g", "$25"),
        ]
        self.assertEqual(self.order(options, 30), ["overshoot", "exact-fit"])

    def test_one_pack_is_enough_when_it_covers(self):
        options = [offer("covers", 50, "g", "$10")]
        self.assertEqual(_total_cost(options[0], 30), (0, 10.0))

    def test_multiple_packs_are_counted(self):
        # 30 g needed, 10 g packs: three bottles, not 1.5.
        options = [offer("small", 10, "g", "$10")]
        self.assertEqual(_total_cost(options[0], 30), (0, 30.0))

    def test_unpriced_offers_sort_last(self):
        """
        An offer with no price is not free, and must never win. It is kept
        rather than dropped because "this supplier has it, price on request"
        is useful to a chemist.
        """
        options = [
            offer("no-price", 25, "g", None),
            offer("expensive", 25, "g", "$999"),
        ]
        self.assertEqual(self.order(options, 10), ["expensive", "no-price"])

    def test_volume_offers_sort_after_comparable_ones(self):
        options = [
            offer("by-volume", 500, "mL", "$5"),
            offer("by-mass", 25, "g", "$50"),
        ]
        self.assertEqual(self.order(options, 10), ["by-mass", "by-volume"])

    def test_no_amount_given_falls_back_to_price(self):
        options = [
            offer("dearer", 25, "g", "$50"),
            offer("cheaper", 25, "g", "$20"),
        ]
        self.assertEqual(self.order(options, None), ["cheaper", "dearer"])


class Failures(unittest.TestCase):
    """
    complete says whether every source ANSWERED, not whether anything was
    found. Those are different questions and conflating them is the bug this
    package had.
    """

    def setUp(self):
        self._real = packprice.SOURCES.copy()

    def tearDown(self):
        packprice.SOURCES = self._real

    def test_empty_from_a_working_source_is_complete(self):
        packprice.SOURCES = {"test": FakeSource(options=[])}
        result = search("CCO", 10)
        self.assertEqual(result.options, [])
        self.assertTrue(result.complete)

    def test_a_broken_source_is_not_complete(self):
        packprice.SOURCES = {
            "test": FakeSource(raises=packprice.SourceError("test", "HTTP 401"))
        }
        result = search("CCO", 10)
        self.assertEqual(result.options, [])
        self.assertFalse(result.complete)
        self.assertIn("401", result.errors["test"])

    def test_one_source_failing_does_not_lose_the_others(self):
        packprice.SOURCES = {
            "good": FakeSource(options=[offer("supplier", 25, "g", "$10")]),
            "bad": FakeSource(raises=packprice.SourceError("bad", "timeout")),
        }
        result = search("CCO", 10)
        self.assertEqual(len(result.options), 1)
        self.assertFalse(result.complete)
        self.assertEqual(result.options[0]["source"], "good")

    def test_a_source_without_a_key_is_skipped_not_failed(self):
        """Not configuring Mcule is a choice. Mcule being down is an incident."""
        unconfigured = FakeSource(options=[])
        unconfigured.API_KEY = ""
        packprice.SOURCES = {"test": unconfigured}
        result = search("CCO", 10)
        self.assertTrue(result.complete)
        self.assertEqual(result.errors, {})


if __name__ == "__main__":
    unittest.main()
