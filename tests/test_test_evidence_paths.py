from __future__ import annotations

import runpy

from discrepancy_desk.test_evidence import pytest_evidence_destination


def test_full_suite_has_stable_evidence_path() -> None:
    assert str(pytest_evidence_destination(("-q",), {})).replace("\\", "/") == (
        "runtime/test-evidence/full-suite.json"
    )


def test_focused_session_does_not_clobber_full_suite() -> None:
    destination = pytest_evidence_destination(("tests/test_example.py", "-q"), {})
    assert destination.name == "tests-test_example.py.json"
    assert "focused" in destination.parts


def test_explicit_hammer_path_wins() -> None:
    destination = pytest_evidence_destination(
        ("tests/test_example.py",),
        {"DISCREPANCY_DESK_PYTEST_EVIDENCE_PATH": "runtime/test-evidence/hammer/HT-01.json"},
    )
    assert destination.as_posix() == "runtime/test-evidence/hammer/HT-01.json"


def test_pytest_option_value_is_not_misclassified_as_target() -> None:
    destination = pytest_evidence_destination(
        ("-o", "addopts=", "--disable-warnings", "-q"), {}
    )
    assert destination.as_posix() == "runtime/test-evidence/full-suite.json"


def test_commit_bound_hammer_payload_ignores_run_time_diagnostics() -> None:
    commit_bound_payload = runpy.run_path("scripts/run_ht_evidence.py")[
        "commit_bound_payload"
    ]
    first = {
        "schema_version": 3,
        "suite": "m06a-phase2",
        "generated_at": "first-time",
        "commit_sha": "a" * 40,
        "working_tree_dirty": False,
        "results": [
            {
                "invariant_id": "M06A-HT-018",
                "passed": True,
                "stdout": "1 passed in 0.10s",
                "stderr": "",
            }
        ],
        "summary": {"passed": 1, "failed": 0},
    }
    second = {
        **first,
        "generated_at": "second-time",
        "results": [
            {
                **first["results"][0],
                "stdout": "1 passed in 0.82s",
                "stderr": "environment warning",
            }
        ],
    }
    assert commit_bound_payload(first) == commit_bound_payload(second)
