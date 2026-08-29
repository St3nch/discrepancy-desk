"""Evidence records.

Reconciliation section 6: "The runner must not silently truncate its own
evidence." Bounds here are therefore fail-closed guards, not truncation. Each
proof produces on the order of tens of rows; exceeding a bound means something
unexpected happened and the run fails rather than quietly shortening the record.

Reconciliation section 8 divides evidence into three classes. Every fact the
report carries is tagged so the Steward can never mistake a VedaOps attestation
for something PostgreSQL proved.
"""

from __future__ import annotations

import datetime as dt
import decimal
import ipaddress
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import ErrorCategory, ProofRunError

#: Per-step row cap. Exceeding it is a failure, never a silent shortening.
MAX_ROWS_PER_STEP = 200

#: Per-value character cap, applied to the JSON rendering of a single value.
MAX_VALUE_CHARS = 4000


class EvidenceClass(StrEnum):
    """Who established a fact (reconciliation section 8)."""

    VEDAOPS_ATTESTED = "vedaops_attested"
    RUNNER_PROVED = "runner_proved"
    STEWARD_INFERRED = "steward_inferred"


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


def jsonable(value: Any) -> Any:
    """Convert a driver value into a JSON-safe, bounded rendering."""
    if value is None or isinstance(value, bool | int | float | str):
        rendered = value
    elif isinstance(value, dt.datetime | dt.date | dt.time):
        rendered = value.isoformat()
    elif isinstance(value, dt.timedelta):
        rendered = value.total_seconds()
    elif isinstance(
        value,
        decimal.Decimal
        | uuid.UUID
        | ipaddress.IPv4Address
        | ipaddress.IPv6Address
        | ipaddress.IPv4Interface
        | ipaddress.IPv6Interface,
    ):
        rendered = str(value)
    elif isinstance(value, bytes | bytearray | memoryview):
        rendered = bytes(value).hex()
    elif isinstance(value, list | tuple):
        return [jsonable(item) for item in value]
    elif isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    else:
        rendered = str(value)

    if isinstance(rendered, str) and len(rendered) > MAX_VALUE_CHARS:
        raise ProofRunError(
            ErrorCategory.EVIDENCE_INCOMPLETE,
            f"a single observed value exceeded the {MAX_VALUE_CHARS}-character evidence "
            "bound; the runner fails rather than truncating evidence",
        )
    return rendered


def bounded_rows(rows: list[Any], label: str) -> list[Any]:
    """Return JSON-safe rows, failing closed if the row bound is exceeded."""
    if len(rows) > MAX_ROWS_PER_STEP:
        raise ProofRunError(
            ErrorCategory.EVIDENCE_INCOMPLETE,
            f"step {label!r} produced {len(rows)} rows, exceeding the "
            f"{MAX_ROWS_PER_STEP}-row evidence bound; the runner fails rather than "
            "truncating evidence",
        )
    return [jsonable(row) for row in rows]


@dataclass(frozen=True)
class Assertion:
    """One expected-versus-observed decision."""

    name: str
    expected: str
    observed: str
    passed: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expected": self.expected,
            "observed": self.observed,
            "passed": self.passed,
        }


def assert_that(name: str, expected: Any, observed: Any) -> Assertion:
    """Build an assertion by exact equality of the rendered values."""
    return Assertion(
        name=name,
        expected=repr(expected),
        observed=repr(observed),
        passed=expected == observed,
    )


@dataclass(frozen=True)
class SqlStep:
    """One executed SQL statement and what PostgreSQL did with it."""

    label: str
    sql: str
    params: dict[str, Any] | None = None
    succeeded: bool = True
    expected_failure: bool = False
    sqlstate: str | None = None
    error_category: str | None = None
    rows: list[Any] = field(default_factory=list)

    @property
    def unexpected(self) -> bool:
        """True when PostgreSQL did the opposite of what the harness expects.

        An adversary that unexpectedly succeeds is a proof failure; so is a
        normal step that unexpectedly fails.
        """
        return self.succeeded == self.expected_failure

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "sql": self.sql,
            "params": {k: jsonable(v) for k, v in (self.params or {}).items()},
            "succeeded": self.succeeded,
            "expected_failure": self.expected_failure,
            "unexpected": self.unexpected,
            "sqlstate": self.sqlstate,
            "error_category": self.error_category,
            "rows": self.rows,
        }


@dataclass
class ProofResult:
    """The complete evidence for one proof."""

    proof: str
    title: str
    database: str | None = None
    preflight: dict[str, Any] = field(default_factory=dict)
    steps: list[SqlStep] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    failure_category: str | None = None
    failure_message: str | None = None
    teardown: dict[str, Any] = field(default_factory=dict)

    @property
    def unexpected_steps(self) -> list[SqlStep]:
        return [step for step in self.steps if step.unexpected]

    @property
    def failed_assertions(self) -> list[Assertion]:
        return [a for a in self.assertions if not a.passed]

    @property
    def outcome(self) -> Outcome:
        """PASS only when nothing failed and at least one assertion ran.

        A proof that recorded no assertions has proved nothing, so it cannot
        pass. That closes the "skipped proof becomes PASS" fail-open path.
        """
        if self.failure_category is not None:
            return Outcome.FAIL
        if not self.assertions:
            return Outcome.FAIL
        if self.failed_assertions or self.unexpected_steps:
            return Outcome.FAIL
        return Outcome.PASS

    def to_json(self) -> dict[str, Any]:
        return {
            "proof": self.proof,
            "title": self.title,
            "outcome": str(self.outcome),
            "evidence_class": str(EvidenceClass.RUNNER_PROVED),
            "database": self.database,
            "preflight": self.preflight,
            "failure_category": self.failure_category,
            "failure_message": self.failure_message,
            "assertions": [a.to_json() for a in self.assertions],
            "failed_assertion_names": [a.name for a in self.failed_assertions],
            "unexpected_step_labels": [s.label for s in self.unexpected_steps],
            "steps": [s.to_json() for s in self.steps],
            "teardown": self.teardown,
        }
