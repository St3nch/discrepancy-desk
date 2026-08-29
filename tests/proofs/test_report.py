"""Report assembly, evidence classification, and the secret scrubber."""

from __future__ import annotations

import json

from tools.postgres_foundation_proofs.evidence import Outcome, ProofResult, assert_that
from tools.postgres_foundation_proofs.report import (
    build_human_summary,
    contaminated_document,
    evidence_responsibility,
    foundation_consequences,
    render,
    scan_for_secrets,
)

ALL_PASS = {"A": Outcome.PASS, "B": Outcome.PASS, "C": Outcome.PASS}
ALL_FAIL = {"A": Outcome.FAIL, "B": Outcome.FAIL, "C": Outcome.FAIL}


def test_clean_text_passes_the_secret_scan():
    assert scan_for_secrets("no secrets here", frozenset({"NOT_A_REAL_PASSWORD"}))["clean"] is True


def test_a_leaked_secret_is_detected():
    scan = scan_for_secrets("host=x pw=NOT_A_REAL_PASSWORD", frozenset({"NOT_A_REAL_PASSWORD"}))
    assert scan["clean"] is False
    assert scan["hits"] == 1


def test_the_scan_result_never_echoes_the_secret():
    scan = scan_for_secrets("NOT_A_REAL_PASSWORD", frozenset({"NOT_A_REAL_PASSWORD"}))
    assert "NOT_A_REAL_PASSWORD" not in json.dumps(scan)


def test_very_short_candidates_are_reported_as_unchecked_not_silently_skipped():
    scan = scan_for_secrets("abc", frozenset({"ab"}))
    assert scan["candidates_unchecked_too_short"] == 1
    assert scan["candidates_checked"] == 0


def test_contaminated_document_suppresses_the_body():
    scan = {"hits": 1, "clean": False}
    document = contaminated_document(scan)
    assert document["error_category"] == "report_contaminated"
    assert "proofs" not in document
    assert "connection" not in document
    assert "suppressed" in document["human_summary"]


def test_foundation_vocabulary_on_a_full_pass():
    consequences = foundation_consequences(ALL_PASS)
    assert consequences["FND-002"]["classification"] == "PARTIAL PHYSICAL EVIDENCE"
    assert (
        consequences["FND-008"]["classification"]
        == "PHYSICAL EVIDENCE FOR THE CANDIDATE PROJECTION"
    )
    assert (
        consequences["FND-010"]["classification"]
        == "PHYSICAL EVIDENCE FOR THE TYPED DEFAULT-DENY CANDIDATE"
    )


def test_items_no_proof_exercises_are_never_claimed():
    for outcomes in (ALL_PASS, ALL_FAIL):
        consequences = foundation_consequences(outcomes)
        assert consequences["FND-009"]["classification"] == "NOT EXERCISED"
        assert consequences["FND-011"]["classification"] == "NOT EXERCISED"


def test_a_failed_proof_yields_no_physical_evidence():
    consequences = foundation_consequences(ALL_FAIL)
    assert consequences["FND-002"]["classification"] == "NO PHYSICAL EVIDENCE"
    assert consequences["FND-008"]["classification"] == "NO PHYSICAL EVIDENCE"
    assert consequences["FND-010"]["classification"] == "NO PHYSICAL EVIDENCE"


def test_passing_sql_never_promotes_an_item():
    assert "never changes an item status automatically" in foundation_consequences(ALL_PASS)["note"]


def test_fnd_002_states_what_it_does_not_cover():
    assert "receipt-finalizer" in foundation_consequences(ALL_PASS)["FND-002"]["does_not_cover"]


def test_evidence_responsibility_separates_the_three_classes():
    responsibility = evidence_responsibility()
    assert "postgres:18-alpine" in " ".join(responsibility["vedaops_attested"])
    assert "independent numeric major-18 check" in responsibility["runner_proved"]
    assert "whether any design may be promoted" in responsibility["steward_inferred"]


def test_host_cluster_claim_is_scoped_to_an_attestation():
    statement = evidence_responsibility()["host_cluster_statement"]
    assert "not a network-level fact proved by SQL" in statement
    assert "No port number alone proves a different server" in statement


def test_container_name_is_not_required():
    assert "Not required" in evidence_responsibility()["container_name"]


def _proof(key: str, passing: bool) -> ProofResult:
    result = ProofResult(proof=key, title="t")
    result.assertions.append(assert_that("x", 1, 1 if passing else 2))
    return result


def test_human_summary_names_failing_assertions():
    summary = build_human_summary(
        Outcome.FAIL, [_proof("A", True), _proof("B", False)], teardown_ok=True
    )
    assert "Proof A" in summary and "PASS" in summary
    assert "failed assertions: x" in summary


def test_human_summary_reports_teardown_and_scope_statements():
    summary = build_human_summary(Outcome.FAIL, [_proof("A", True)], teardown_ok=False)
    assert "teardown: FAILED" in summary
    assert "No production Desk database or schema was created" in summary
    assert "FND-009 and FND-011 are NOT EXERCISED" in summary


def test_render_produces_parseable_json():
    assert json.loads(render({"a": 1}))["a"] == 1
