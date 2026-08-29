"""The numeric PostgreSQL 18 gate.

Harness section 1.3 requires a numeric assertion and forbids inferring the
version from Docker metadata or presentation text.
"""

from __future__ import annotations

import pytest

from tools.postgres_foundation_proofs.errors import ErrorCategory, ProofRunError
from tools.postgres_foundation_proofs.preflight import (
    major_from_server_version_num,
    require_major_18,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("180000", 18), ("180001", 18), ("189999", 18), ("170004", 17), ("1800001", 180)],
)
def test_major_is_computed_numerically(raw, expected):
    assert major_from_server_version_num(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "   ", "abc", "18.1", "-180001", "18_0001", None, 180001, 18.0]
)
def test_non_integer_text_is_refused_rather_than_guessed(raw):
    with pytest.raises(ProofRunError) as excinfo:
        major_from_server_version_num(raw)
    assert excinfo.value.category is ErrorCategory.VERSION_GATE_FAILED


def test_major_18_passes_the_gate():
    assert require_major_18("180001", context="test") == 18


@pytest.mark.parametrize("raw", ["170004", "160010", "190000", "1800001"])
def test_any_other_major_fails_closed(raw):
    with pytest.raises(ProofRunError) as excinfo:
        require_major_18(raw, context="test")
    assert excinfo.value.category is ErrorCategory.VERSION_GATE_FAILED
    assert "requires exactly 18" in excinfo.value.message


def test_presentation_text_cannot_satisfy_the_gate():
    # The version banner must never be accepted in place of server_version_num.
    with pytest.raises(ProofRunError):
        require_major_18("PostgreSQL 18.1 on x86_64-pc-linux-musl", context="test")
