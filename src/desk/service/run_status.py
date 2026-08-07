"""Canonical run status vocabulary (ADR 8 / D12).

Use the full set from the start. Ticket 03 only transitions draft → approved →
claimed; abandoned/suspended/complete/cancelled remain in the vocabulary so
later tickets do not invent a local subset (codingstandards vocabulary check).
"""

from __future__ import annotations

from typing import Final, Literal

RunStatus = Literal[
    "draft",
    "approved",
    "claimed",
    "suspended",
    "complete",
    "abandoned",
    "cancelled",
]

RUN_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "draft",
        "approved",
        "claimed",
        "suspended",
        "complete",
        "abandoned",
        "cancelled",
    }
)

# Statuses that mean a case is still "in flight" for serialisation (D12):
# claimable, under lease, or waiting on a human mid-flight. At most one per case.
ACTIVE_CLAIM_STATUSES: Final[frozenset[str]] = frozenset({"approved", "claimed", "suspended"})

PLACEHOLDER_RUBRIC_VERSION: Final[str] = "0"
PLACEHOLDER_RUBRIC_TEXT: Final[str] = (
    "Placeholder rubric; standing questions not yet drafted for this operation."
)
