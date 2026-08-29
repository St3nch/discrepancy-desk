"""Hard client-side deadlines for every concurrency wait and observer poll.

Reconciliation section 6 requires a hard client-side deadline on every wait. The
clock is injectable so deadline behavior is deterministically testable without
sleeping and without a database.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from .errors import DeadlineExceeded


class Deadline:
    """A monotonic budget that fails closed when exhausted."""

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        if seconds <= 0:
            raise ValueError("deadline seconds must be positive")
        self._clock = clock
        self._seconds = float(seconds)
        self._start = clock()

    @property
    def seconds(self) -> float:
        return self._seconds

    def elapsed(self) -> float:
        return self._clock() - self._start

    def remaining(self) -> float:
        return self._seconds - self.elapsed()

    def expired(self) -> bool:
        return self.remaining() <= 0

    def check(self, what: str) -> None:
        """Raise if the budget is exhausted."""
        if self.expired():
            raise DeadlineExceeded(
                f"hard client-side deadline of {self._seconds:g}s exceeded while waiting for {what}"
            )
