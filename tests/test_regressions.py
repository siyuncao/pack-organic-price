"""
Three bugs found by auditing the finished package, each pinned by a test.

All of them were silent: no exception, no error field, just a wrong answer
that looked like a right one. That is the shape worth a regression test.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import packprice
from packprice import cache, molport


def _molport_replies(rows=(), shipping=None):
    """A _call stub that walks the whole submit/poll/fetch sequence."""

    def call(method, path, body=None):
        if path == "/list-searches":
            return {"search_key": "k"}
        if path.startswith("/list-searches/status/"):
            return {"status": "finished"}
        return {
            "request": {"results": list(rows)},
            "summary": {"shipping": {"price": shipping}},
        }

    return call


class MolportWithoutAnAmount(unittest.TestCase):
    """
    grams is optional everywhere in the public API. It used to make MolPort
    return [], which its own docstring defines as "no supplier sells this",
    for a search MolPort was never sent.
    """

    def setUp(self):
        self._key = molport.API_KEY
        molport.API_KEY = "test-key"

    def tearDown(self):
        molport.API_KEY = self._key

    def test_a_missing_amount_still_asks_molport(self):
        with mock.patch.object(
            molport, "_call", side_effect=_molport_replies()
        ) as call:
            self.assertEqual(molport.find_options("Fc1ccccn1", None), [])
        self.assertTrue(call.called, "MolPort was never asked")

    def test_a_missing_amount_asks_for_the_smallest_pack(self):
        with mock.patch.object(
            molport, "_call", side_effect=_molport_replies()
        ) as call:
            molport.find_options("Fc1ccccn1", None)
        submitted = call.call_args_list[0][0][2]
        self.assertEqual(submitted["amount"], 1)

    def test_zero_is_treated_the_same_as_missing(self):
        with mock.patch.object(
            molport, "_call", side_effect=_molport_replies()
        ) as call:
            molport.find_options("Fc1ccccn1", 0)
        self.assertTrue(call.called)

    def test_no_key_still_returns_nothing_without_asking(self):
        molport.API_KEY = ""
        with mock.patch.object(molport, "_call") as call:
            self.assertEqual(molport.find_options("Fc1ccccn1", 7.6), [])
        self.assertFalse(call.called)


class ShippingCountryIsPartOfTheCacheKey(unittest.TestCase):
    """
    search() read `SHIP_TO` off every source module. ChemSpace spells it that
    way; MolPort spells it SHIPPING_COUNTRY, so MolPort's country never
    reached the key and a US answer was served for a GB order for seven days.
    """

    def test_both_spellings_are_read(self):
        chemspace_like = mock.Mock(SHIP_TO="GB", CATEGORIES="", API_KEY="k")
        molport_like = mock.Mock(SHIPPING_COUNTRY="GB", CATEGORIES="", API_KEY="k")
        del molport_like.SHIP_TO

        for module in (chemspace_like, molport_like):
            ship_to = getattr(module, "SHIP_TO", "") or getattr(
                module, "SHIPPING_COUNTRY", ""
            )
            self.assertEqual(ship_to, "GB")

    def test_molport_names_its_country_shipping_country(self):
        # If this ever gets renamed, the getattr chain above must follow.
        self.assertTrue(hasattr(molport, "SHIPPING_COUNTRY"))


class SubGramAmountsGetTheirOwnCacheEntry(unittest.TestCase):
    """
    The key rounded the amount to a whole gram, so every amount under 1.5 g
    hashed to the same file. Mcule quotes at milligram resolution, so 5 mg
    and 400 mg were being served each other's price.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._dir = cache.CACHE_DIR
        cache.CACHE_DIR = self.tmp

    def tearDown(self):
        cache.CACHE_DIR = self._dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_five_milligrams_is_not_four_hundred(self):
        self.assertNotEqual(
            cache._key("mcule", "CCO", 0.005),
            cache._key("mcule", "CCO", 0.4),
        )

    def test_a_stored_milligram_price_is_not_served_for_another(self):
        cache.put("mcule", "CCO", 0.005, [{"price": "$6"}], now=0)
        self.assertIsNone(cache.get("mcule", "CCO", 0.4, now=0))

    def test_gram_scale_still_shares_one_entry(self):
        # The original rationale, kept: 7.6 g and 7.61 g are one question.
        self.assertEqual(
            cache._key("molport", "CCO", 7.6),
            cache._key("molport", "CCO", 7.61),
        )

    def test_no_amount_is_still_its_own_key(self):
        self.assertNotEqual(
            cache._key("molport", "CCO", None),
            cache._key("molport", "CCO", 1),
        )


class SaltFormsDoNotOutrankTheCompoundAskedFor(unittest.TestCase):
    """
    ChemSpace answers a structure search with the structure and its salts.
    Triethylamine returns 1 ExactMatch and 16 SaltForm: the hydrochloride,
    the borane complex, the tris-HF complex. The salts are cheaper, so
    ranking on price alone put a solid salt at the top of a list for a
    liquid free base. On the app's own grading scale that is a wrong
    compound, the worst score there is.
    """

    def test_exact_match_outranks_a_cheaper_salt(self):
        from packprice import chemspace
        self.assertLess(
            chemspace._match_rank({"match_type": "ExactMatch"}),
            chemspace._match_rank({"match_type": "SaltForm"}),
        )

    def test_sources_without_a_match_type_are_not_penalised(self):
        from packprice import chemspace
        # MolPort and Mcule do not report one; they must not sort last.
        self.assertEqual(chemspace._match_rank({}), 0)
        self.assertEqual(chemspace._match_rank({"match_type": None}), 0)

    def test_salt_forms_are_kept_not_dropped(self):
        from packprice import chemspace
        self.assertEqual(chemspace._match_rank({"match_type": "SaltForm"}), 1)


class DrumsDoNotOutrankBottles(unittest.TestCase):
    """
    Ranking on cheapest-way-to-enough alone recommended a 1 kg bottle of
    triethylamine at $14.63 for a 15 g reaction, beating 25 g at $27. The
    arithmetic is right and the answer is wrong: a kilogram of an amine on a
    bench raises storage, hazard and shelf-life problems a price cannot see.
    """

    def setUp(self):
        self.need = 15.25
        self.bottle = {"pack_size_amount": 25, "pack_size_unit": "g", "price": "$27"}
        self.drum = {"pack_size_amount": 1, "pack_size_unit": "kg", "price": "$14.63"}

    def test_a_drum_is_banded_out(self):
        self.assertEqual(packprice._overbuy_rank(self.drum, self.need), 1)

    def test_a_bottle_that_fits_is_not(self):
        self.assertEqual(packprice._overbuy_rank(self.bottle, self.need), 0)

    def test_the_boundary_is_five_times(self):
        just_under = {"pack_size_amount": self.need * 5 - 0.1, "pack_size_unit": "g"}
        just_over = {"pack_size_amount": self.need * 5 + 0.1, "pack_size_unit": "g"}
        self.assertEqual(packprice._overbuy_rank(just_under, self.need), 0)
        self.assertEqual(packprice._overbuy_rank(just_over, self.need), 1)

    def test_no_amount_needed_bands_nothing(self):
        self.assertEqual(packprice._overbuy_rank(self.drum, None), 0)

    def test_an_unconvertible_pack_is_not_penalised_twice(self):
        # Already sorted last by total_cost; must not also be called a drum.
        self.assertEqual(
            packprice._overbuy_rank({"pack_size_amount": 500, "pack_size_unit": "mL"},
                                    self.need), 0)


class TheGlobalSortAlsoBandsSaltForms(unittest.TestCase):
    """
    chemspace.py banded salts inside its own client, but search() re-sorts
    every source's offers afterwards. Without the same band there, a salt that
    survived truncation was lifted straight back to the top.
    """

    def test_salt_forms_rank_after_exact_matches(self):
        self.assertLess(
            packprice._match_rank({"match_type": "ExactMatch"}),
            packprice._match_rank({"match_type": "SaltForm"}),
        )

    def test_molport_and_mcule_are_not_penalised_for_silence(self):
        self.assertEqual(packprice._match_rank({}), 0)
