"""
One exception type, so a source that breaks says so.

Every network call here can fail in ways that are not the caller's fault:
the marketplace is down, the key expired, the search timed out. The tempting
thing is to catch those and return an empty list, because the signature stays
clean and nothing crashes.

That is a lie, and an expensive one. "No supplier sells this" and "we could
not reach the supplier" lead a chemist to opposite decisions: the first means
find another route, the second means try again in an hour. Collapsing them
into [] throws away the difference and cannot be recovered downstream.
"""


class SourceError(Exception):
    """A marketplace could not be reached or refused the request."""

    def __init__(self, source: str, detail: str):
        self.source = source
        self.detail = detail
        super().__init__(f"{source}: {detail}")
