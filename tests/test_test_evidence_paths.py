from __future__ import annotations

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
