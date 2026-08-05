"""Typed refusal contract for governed operations."""

from __future__ import annotations


class DeskRefusal(Exception):
    """Domain refusal. Transports render these; never leak driver/stack details."""

    def __init__(
        self,
        code: str,
        what_happened: str,
        what_was_preserved: str,
        what_was_not_changed: str,
        what_you_can_do: str,
    ) -> None:
        self.code = code
        self.what_happened = what_happened
        self.what_was_preserved = what_was_preserved
        self.what_was_not_changed = what_was_not_changed
        self.what_you_can_do = what_you_can_do
        super().__init__(code)

    def __str__(self) -> str:
        return f"{self.code}: {self.what_happened}"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "what_happened": self.what_happened,
            "what_was_preserved": self.what_was_preserved,
            "what_was_not_changed": self.what_was_not_changed,
            "what_you_can_do": self.what_you_can_do,
        }
