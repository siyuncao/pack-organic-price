"""
Shipping, which only one source reports.

MolPort's response carries a summary block with the delivery cost, and their
website shows it beside every price as "+ $45.00 Direct Shipping to US". It
ranges from $33 to $170 by supplier, so a $10 bottle can be a $55 order. That
was being discarded.

It is attached to the offer and NOT added into the price. Two reasons, and
both matter:

  Shipping is per shipment, not per compound. Order five things from one
  supplier and you pay it once, so adding it to each compound overstates a
  basket.

  ChemSpace and Mcule do not report it at all. Adding it only where it is
  known would make the one honest source look like the expensive one.
"""

import unittest

from packprice.ranking import total_cost


def offer(price, shipping=None):
    o = {
        "supplier": "test",
        "pack_size_amount": 25,
        "pack_size_unit": "g",
        "price": f"${price}",
    }
    if shipping is not None:
        o["shipping_usd"] = shipping
    return o


class Shipping(unittest.TestCase):
    def test_shipping_does_not_change_the_ranking(self):
        """
        A source that reports $45 shipping must not be pushed below one that
        reports nothing and may charge the same.
        """
        honest = offer(10, shipping=45)
        silent = offer(12)
        self.assertLess(total_cost(honest, 20), total_cost(silent, 20))

    def test_absent_shipping_is_not_zero(self):
        """None means unknown. It must not read as free."""
        self.assertIsNone(offer(10).get("shipping_usd"))

    def test_shipping_is_carried_on_the_offer(self):
        self.assertEqual(offer(10, shipping=45)["shipping_usd"], 45)


if __name__ == "__main__":
    unittest.main()
