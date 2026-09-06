"""
Liquids, which suppliers quote both ways.

Fluorochem lists 2-fluoropyridine as 25 g. Acros lists the same compound as
5 ml. Without a density those two cannot be compared, so every volume-quoted
bottle sorted below every mass-quoted one, however cheap it was: a 500 mL
bottle at $30 lost to a 25 g bottle at $1,600.

Passing a density makes them comparable. Not passing one keeps the old, safe
behaviour: sort it last rather than guess at a conversion.
"""

import unittest

from packprice.ranking import grams_of, total_cost


def bottle(amount, unit, price):
    return {
        "supplier": f"{amount}{unit}",
        "pack_size_amount": amount,
        "pack_size_unit": unit,
        "price": f"${price}",
    }


class Conversion(unittest.TestCase):
    def test_millilitres_need_a_density(self):
        self.assertIsNone(grams_of(bottle(500, "ml", 30)))

    def test_millilitres_convert_with_one(self):
        # 2-fluoropyridine, density 1.126 g/mL
        self.assertAlmostEqual(grams_of(bottle(500, "ml", 30), 1.126), 563.0)

    def test_litres_convert(self):
        self.assertAlmostEqual(grams_of(bottle(2, "l", 30), 0.866), 1732.0)

    def test_mass_units_ignore_density(self):
        """A 25 g bottle is 25 g whatever the liquid weighs."""
        self.assertEqual(grams_of(bottle(25, "g", 30), 1.126), 25.0)
        self.assertEqual(grams_of(bottle(25, "g", 30)), 25.0)

    def test_unknown_units_stay_unknown(self):
        self.assertIsNone(grams_of(bottle(5, "umol", 30), 1.126))


class RankingLiquids(unittest.TestCase):
    def setUp(self):
        self.by_volume = bottle(500, "ml", 30)
        self.by_mass = bottle(25, "g", 1600)

    def test_without_density_the_cheap_bottle_loses(self):
        """The old behaviour, kept deliberately: no density, no comparison."""
        self.assertGreater(
            total_cost(self.by_volume, 100), total_cost(self.by_mass, 100)
        )

    def test_with_density_the_cheap_bottle_wins(self):
        self.assertLess(
            total_cost(self.by_volume, 100, 1.126),
            total_cost(self.by_mass, 100, 1.126),
        )

    def test_multiple_bottles_are_counted(self):
        """Needing 200 g of something at 0.866 g/mL: one 100 mL bottle is 86.6 g."""
        small = bottle(100, "ml", 10)
        self.assertEqual(total_cost(small, 200, 0.866), (0, 30.0))  # three bottles


if __name__ == "__main__":
    unittest.main()
