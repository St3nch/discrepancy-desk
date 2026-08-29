"""Report assembly, evidence classification, and the secret scrubber.

Reconciliation section 7: the governed task emits one bounded machine-readable
JSON document to stdout, including a concise ``human_summary`` field, and no
report is written into tracked repository paths.

Reconciliation section 8 requires that VedaOps attestations, runner-proved
facts, and Steward inferences never blur together. Section 9 fixes the
foundation-item consequence vocabulary so passing SQL cannot look like a
promotion.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import ErrorCategory
from .evidence import EvidenceClass, Outcome, ProofResult

REPORT_VERSION = 1

#: Substring checks shorter than this would false-positive against ordinary
#: report text, so they are reported as unchecked rather than silently skipped.
MIN_SCRUB_CANDIDATE_LENGTH = 4


def evidence_responsibility() -> dict[str, Any]:
    """The reconciliation section 8 division, carried in every report."""
    return {
        "note": (
            "VedaOps owns the disposable container substrate. The runner does not start "
            "or inspect Docker. These three classes must not be conflated."
        ),
        str(EvidenceClass.VEDAOPS_ATTESTED): [
            "fixed image postgres:18-alpine",
            "unique disposable container",
            "--rm",
            "no persistent volume",
            "proof-only random credential",
            "random loopback publication",
            "container readiness",
            "VedaOps-side major-18 check",
            "final container removal/cleanup status",
            "host-installed PostgreSQL was not selected as the substrate",
        ],
        str(EvidenceClass.RUNNER_PROVED): [
            "successful connection to the supplied DSN",
            "independent numeric major-18 check",
            "per-proof database creation and isolation",
            "SQL behavior and observed rows",
            "expected-versus-observed assertions",
            "proof-database teardown",
            "credential-free SQL-visible server context",
        ],
        str(EvidenceClass.STEWARD_INFERRED): [
            "what these observations mean for foundation items",
            "whether any design may be promoted",
        ],
        "host_cluster_statement": (
            "The runner did not select the host-installed PostgreSQL cluster: it connects "
            "only to VEDAOPS_POSTGRES_URL and never falls back. The stronger statement that "
            "the host-installed cluster was not used as the substrate is an attestation from "
            "the fixed VedaOps host-operation contract, not a network-level fact proved by "
            "SQL. No port number alone proves a different server."
        ),
        "container_name": (
            "Not required. The governed VedaOps tool intentionally does not expose its "
            "internal container name; the Steward combines the VedaOps tool result with "
            "this report."
        ),
    }


def foundation_consequences(outcomes: dict[str, Outcome]) -> dict[str, Any]:
    """Classify affected foundation items using the section 9 vocabulary."""
    a_pass = outcomes.get("A") is Outcome.PASS
    b_pass = outcomes.get("B") is Outcome.PASS
    c_pass = outcomes.get("C") is Outcome.PASS

    return {
        "note": (
            "Passing SQL never changes an item status automatically. These are physical "
            "evidence classifications, not promotions; promotion is a Steward act."
        ),
        "FND-002": {
            "classification": ("PARTIAL PHYSICAL EVIDENCE" if a_pass else "NO PHYSICAL EVIDENCE"),
            "covers": (
                "serialized ordinal allocation under the lock-first governed admission "
                "gate, and rollback gaps"
            ),
            "does_not_cover": (
                "the civil-time / admission-boundary receipt-finalizer question. No proof "
                "in FND-PG01 exercises a commit-timestamp finalizer."
            ),
            "source_proof": "A",
        },
        "FND-008": {
            "classification": (
                "PHYSICAL EVIDENCE FOR THE CANDIDATE PROJECTION"
                if b_pass
                else "NO PHYSICAL EVIDENCE"
            ),
            "covers": (
                "deterministic boundary projection, explicit supersession, visible conflict "
                "without arbitrary partitioning, and historical reconstruction"
            ),
            "does_not_cover": ("promotion of the open-design item to resolved authority"),
            "source_proof": "B",
        },
        "FND-009": {
            "classification": "NOT EXERCISED",
            "covers": None,
            "does_not_cover": (
                "Proof C manually inserts dependency rows; it does not test automatic "
                "dependency capture for derived state."
            ),
            "source_proof": None,
        },
        "FND-010": {
            "classification": (
                "PHYSICAL EVIDENCE FOR THE TYPED DEFAULT-DENY CANDIDATE"
                if c_pass
                else "NO PHYSICAL EVIDENCE"
            ),
            "covers": (
                "typed FK edge tables, reverse indexes, read-only UNION traversal view, and "
                "default-deny rejection of an unlisted relation kind"
            ),
            "does_not_cover": "the full allowed provenance matrix for every slice noun",
            "source_proof": "C",
        },
        "FND-011": {
            "classification": "NOT EXERCISED",
            "covers": None,
            "does_not_cover": (
                "FK/CHECK/view enforcement is not append-only privilege or trigger "
                "enforcement. No proof touches roles, privileges, or defensive triggers."
            ),
            "source_proof": None,
        },
    }


def scan_for_secrets(text: str, candidates: frozenset[str]) -> dict[str, Any]:
    """Defence-in-depth secret check over the rendered report.

    Returns only counts and lengths. The matched value is never echoed, because
    echoing it would be the very leak this check exists to prevent.
    """
    checked = 0
    unchecked_short = 0
    hits = 0
    for candidate in candidates:
        if len(candidate) < MIN_SCRUB_CANDIDATE_LENGTH:
            unchecked_short += 1
            continue
        checked += 1
        if candidate in text:
            hits += 1
    return {
        "candidates_checked": checked,
        "candidates_unchecked_too_short": unchecked_short,
        "hits": hits,
        "clean": hits == 0,
    }


def build_human_summary(
    overall: Outcome,
    proofs: list[ProofResult],
    teardown_ok: bool,
) -> str:
    """A concise operator-readable summary carried inside the JSON document."""
    lines = [f"FND-PG01 PostgreSQL 18 foundation proofs: {overall}."]
    for proof in proofs:
        detail = ""
        if proof.outcome is Outcome.FAIL:
            reasons = []
            if proof.failure_category:
                reasons.append(proof.failure_category)
            if proof.failed_assertions:
                reasons.append(
                    "failed assertions: " + ", ".join(a.name for a in proof.failed_assertions)
                )
            if proof.unexpected_steps:
                reasons.append(
                    "unexpected steps: " + ", ".join(s.label for s in proof.unexpected_steps)
                )
            detail = f" ({'; '.join(reasons)})" if reasons else ""
        lines.append(f"  Proof {proof.proof} {proof.title}: {proof.outcome}{detail}")
    lines.append(f"  Proof-database teardown: {'all dropped' if teardown_ok else 'FAILED'}.")
    lines.append(
        "  No production Desk database or schema was created. The runner connected only to "
        "VEDAOPS_POSTGRES_URL and never selected the host-installed PostgreSQL cluster."
    )
    lines.append(
        "  FND-009 and FND-011 are NOT EXERCISED by these proofs. FND-002 receives partial "
        "physical evidence only. Promotion remains a Steward act."
    )
    return "\n".join(lines)


def render(document: dict[str, Any]) -> str:
    """Serialize the report deterministically."""
    return json.dumps(document, indent=2, ensure_ascii=False)


def contaminated_document(scan: dict[str, Any]) -> dict[str, Any]:
    """The only document emitted when the secret check trips.

    The body is suppressed rather than redacted in place, because a partial
    redaction of an unknown leak path is not a safe assumption.
    """
    return {
        "report_version": REPORT_VERSION,
        "ticket": "FND-PG01",
        "result": str(Outcome.FAIL),
        "error_category": str(ErrorCategory.REPORT_CONTAMINATED),
        "secret_scan": scan,
        "human_summary": (
            "FND-PG01 report suppressed: the defence-in-depth secret check found credential "
            "material in the rendered report. No report body is emitted. This is a runner "
            "defect and must be fixed before commissioning."
        ),
    }
