"""
Rate limiting, tested against a fake clock instead of by waiting.

ChemSpace allows 40 requests a minute and reports the state of that budget in
headers on every response. The logic here is: believe the server, wait only
when it says there is nothing left, and never guess.

None of these tests sleep. _wait_needed is pure — it takes the current time
as an argument — so a whole window can be tested in microseconds.
"""

import unittest

from packprice import chemspace


class Headers(dict):
    """urllib response headers are dict-like and case-insensitive enough."""


class Quota(unittest.TestCase):
    def setUp(self):
        chemspace._quota.update({"remaining": None, "reset_at": 0.0})

    def test_unknown_quota_does_not_wait(self):
        """Before the first response we know nothing, so we go ahead."""
        self.assertEqual(chemspace._wait_needed(now=1000), 0.0)

    def test_headroom_does_not_wait(self):
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "12", "X-Rate-Limit-Reset": "30"}),
            now=1000,
        )
        self.assertEqual(chemspace._wait_needed(now=1000), 0.0)

    def test_one_left_still_does_not_wait(self):
        """The quota exists to be used. Slowing down early is guessing."""
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "1", "X-Rate-Limit-Reset": "30"}),
            now=1000,
        )
        self.assertEqual(chemspace._wait_needed(now=1000), 0.0)

    def test_exhausted_waits_until_reset(self):
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "42"}),
            now=1000,
        )
        self.assertEqual(chemspace._wait_needed(now=1000), 42.0)

    def test_wait_shrinks_as_time_passes(self):
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "60"}),
            now=1000,
        )
        self.assertEqual(chemspace._wait_needed(now=1030), 30.0)

    def test_never_waits_a_negative_time(self):
        """A window that already closed is not a wait of minus ten seconds."""
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "10"}),
            now=1000,
        )
        self.assertEqual(chemspace._wait_needed(now=1020), 0.0)

    def test_missing_headers_are_ignored(self):
        """Not every response carries them. Absence is not zero remaining."""
        chemspace._note_quota(Headers({}), now=1000)
        self.assertIsNone(chemspace._quota["remaining"])
        self.assertEqual(chemspace._wait_needed(now=1000), 0.0)

    def test_nonsense_headers_are_ignored(self):
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "lots", "X-Rate-Limit-Reset": "soon"}),
            now=1000,
        )
        self.assertIsNone(chemspace._quota["remaining"])

    def test_errors_update_the_quota_too(self):
        """
        A 429 carries the headers as well, and it is the response that most
        needs reading. Ignoring headers on failures is how a client ends up
        retrying straight into the same wall.
        """
        chemspace._note_quota(
            Headers({"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "15"}),
            now=2000,
        )
        self.assertEqual(chemspace._wait_needed(now=2000), 15.0)


if __name__ == "__main__":
    unittest.main()
