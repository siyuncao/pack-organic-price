"""
The cache, tested with a temporary directory and a fake clock.

Nothing here sleeps or waits a week. Every function that cares about time
takes `now` as an argument, so seven days is a number rather than a delay.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from packprice import cache

DAY = 86400


class CacheBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._dir, self._age = cache.CACHE_DIR, cache.MAX_AGE_DAYS
        cache.CACHE_DIR = self.tmp
        cache.MAX_AGE_DAYS = 7.0
        self.offers = [{"supplier": "A2B", "price": "$10"}]

    def tearDown(self):
        cache.CACHE_DIR, cache.MAX_AGE_DAYS = self._dir, self._age
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_miss_before_anything_is_stored(self):
        self.assertIsNone(cache.get("molport", "CCO", 10))

    def test_hit_after_storing(self):
        cache.put("molport", "CCO", 10, self.offers, now=1000)
        got = cache.get("molport", "CCO", 10, now=1000)
        self.assertEqual(got[0]["supplier"], "A2B")

    def test_fresh_within_the_window(self):
        cache.put("molport", "CCO", 10, self.offers, now=0)
        self.assertIsNotNone(cache.get("molport", "CCO", 10, now=6 * DAY))

    def test_stale_past_the_window(self):
        cache.put("molport", "CCO", 10, self.offers, now=0)
        self.assertIsNone(cache.get("molport", "CCO", 10, now=8 * DAY))

    def test_an_honest_empty_result_is_cached(self):
        """
        MolPort having no offer for TEMPO is a finding, not a failure, and
        re-asking it every run wastes a request. None means "ask"; [] means
        "asked recently, nothing there".
        """
        cache.put("molport", "TEMPO", 26, [], now=1000)
        self.assertEqual(cache.get("molport", "TEMPO", 26, now=1000), [])

    def test_sources_do_not_share_entries(self):
        cache.put("molport", "CCO", 10, self.offers, now=1000)
        self.assertIsNone(cache.get("chemspace", "CCO", 10, now=1000))

    def test_config_is_part_of_the_key(self):
        """Shipping to the US and to the UK are different questions."""
        cache.put("chemspace", "CCO", 10, self.offers, config="US:CSSB", now=1000)
        self.assertIsNone(
            cache.get("chemspace", "CCO", 10, config="GB:CSSB", now=1000)
        )

    def test_similar_amounts_share_an_entry(self):
        """7.6 g and 7.61 g are the same question. Rounded to the gram."""
        cache.put("molport", "CCO", 7.6, self.offers, now=1000)
        self.assertIsNotNone(cache.get("molport", "CCO", 7.61, now=1000))

    def test_different_amounts_do_not(self):
        cache.put("molport", "CCO", 5, self.offers, now=1000)
        self.assertIsNone(cache.get("molport", "CCO", 500, now=1000))

    def test_options_carry_their_age(self):
        cache.put("molport", "CCO", 10, self.offers, now=0)
        option = cache.get("molport", "CCO", 10, now=3 * DAY)[0]
        self.assertAlmostEqual(cache.age_days(option, now=3 * DAY), 3.0)

    def test_a_live_option_has_no_age(self):
        self.assertIsNone(cache.age_days({"supplier": "A2B"}))

    def test_disabled_cache_stores_nothing(self):
        cache.MAX_AGE_DAYS = 0
        cache.put("molport", "CCO", 10, self.offers, now=1000)
        self.assertIsNone(cache.get("molport", "CCO", 10, now=1000))

    def test_corrupt_entry_is_a_miss_not_a_crash(self):
        cache.put("molport", "CCO", 10, self.offers, now=1000)
        for path in self.tmp.glob("*.json"):
            path.write_text("{ not json")
        self.assertIsNone(cache.get("molport", "CCO", 10, now=1000))

    def test_clear_removes_everything(self):
        cache.put("molport", "CCO", 10, self.offers, now=1000)
        cache.put("chemspace", "CCO", 10, self.offers, now=1000)
        self.assertEqual(cache.clear(), 2)
        self.assertIsNone(cache.get("molport", "CCO", 10, now=1000))


if __name__ == "__main__":
    unittest.main()
