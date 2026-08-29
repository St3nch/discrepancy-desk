"""The governed task contract.

Reconciliation sections 7 and 10: the task is flagless, reads the DSN only from
the environment, emits one bounded JSON document with a ``human_summary`` to
stdout, and never falls back to another server.

None of these tests contacts a database. Each exercises a path that fails closed
before any connection is attempted.
"""

from __future__ import annotations

import json

import pytest

from tools.postgres_foundation_proofs.dsn import DSN_ENVIRONMENT_VARIABLE
from tools.postgres_foundation_proofs.runner import (
    EXIT_PRECONDITION_FAILED,
    EXIT_REPORT_CONTAMINATED,
    FIXED_ARGV,
    main,
)


@pytest.fixture(autouse=True)
def _no_inherited_dsn(monkeypatch):
    """Never let a developer's environment point these tests at a real server."""
    monkeypatch.delenv(DSN_ENVIRONMENT_VARIABLE, raising=False)


def _run(argv, capsys):
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    "argv",
    [
        ["--proof", "A"],
        ["--dsn", "postgresql://u:p@127.0.0.1:5432/postgres"],
        ["--host", "127.0.0.1"],
        ["--skip-teardown"],
        ["--report", "/tmp/report.json"],
        ["--allow-any-version"],
        ["extra"],
    ],
)
def test_the_task_accepts_no_arguments(argv, capsys):
    code, document = _run(argv, capsys)
    assert code == EXIT_PRECONDITION_FAILED
    assert document["result"] == "FAIL"
    assert "flagless by contract" in document["human_summary"]


def test_a_dsn_supplied_through_argv_is_refused(capsys):
    secret = "NOT_A_REAL_PASSWORD"
    code, document = _run([f"postgresql://u:{secret}@127.0.0.1:5432/postgres"], capsys)
    assert code == EXIT_PRECONDITION_FAILED
    assert secret not in json.dumps(document)


def test_missing_dsn_refuses_without_contacting_any_server(capsys):
    code, document = _run([], capsys)
    assert code == EXIT_PRECONDITION_FAILED
    assert document["error_category"] == "dsn_missing"
    assert "never selects a default DSN" in document["error_message"]
    assert "No proof database was created" in document["human_summary"]


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-dsn",
        "postgresql:///postgres",
        "postgresql://u:p@127.0.0.1/postgres",
        "postgresql://u:p@127.0.0.1:5432/postgres?service=elsewhere",
    ],
)
def test_a_rejected_dsn_never_reaches_a_connection(raw, capsys, monkeypatch):
    monkeypatch.setenv(DSN_ENVIRONMENT_VARIABLE, raw)
    code, document = _run([], capsys)
    assert code == EXIT_PRECONDITION_FAILED
    assert document["error_category"] in {"dsn_unparseable", "dsn_rejected"}


def test_every_report_carries_a_human_summary(capsys):
    _code, document = _run([], capsys)
    assert isinstance(document["human_summary"], str)
    assert document["human_summary"]


def test_the_document_is_a_single_json_object(capsys):
    main([])
    out = capsys.readouterr().out
    assert out.count("\n{") == 0  # exactly one top-level document
    json.loads(out)


def test_fixed_argv_matches_the_live_vedaops_binding():
    # Must equal the finalized external task binding exactly.
    assert FIXED_ARGV == [
        "uv",
        "run",
        "--offline",
        "--no-sync",
        "python",
        "-m",
        "tools.postgres_foundation_proofs",
    ]


def test_fixed_argv_carries_no_credential_or_connection_input():
    joined = " ".join(FIXED_ARGV)
    for forbidden in ("postgres://", "postgresql://", "password", "@", "127.0.0.1"):
        assert forbidden not in joined


def test_the_only_flags_are_uv_environment_policy_not_proof_inputs():
    # The task takes no caller flags. The two present belong to uv: --offline
    # forbids network access, --no-sync forbids runtime provisioning.
    flags = [arg for arg in FIXED_ARGV if arg.startswith("-") and arg != "-m"]
    assert flags == ["--offline", "--no-sync"]


def test_fixed_argv_pins_no_absolute_interpreter_path():
    # `uv` is resolved from the task environment; the repository must not pin a
    # machine-specific interpreter path that can drift from operator policy.
    assert FIXED_ARGV[0] == "uv"
    assert not any(arg.startswith("/") for arg in FIXED_ARGV)


def test_fixed_argv_cannot_install_or_resolve_dependencies():
    joined = " ".join(FIXED_ARGV)
    for forbidden in ("sync", "install", "add", "pip", "--frozen"):
        assert forbidden not in joined.replace("--no-sync", "")


def test_the_printed_document_is_the_scanned_document(capsys, monkeypatch):
    # The scrubber must verify the exact bytes it prints, not an earlier
    # rendering that lacked the scan result.
    monkeypatch.setenv(DSN_ENVIRONMENT_VARIABLE, "not-a-dsn")
    main([])
    document = json.loads(capsys.readouterr().out)
    assert document["secret_scan"]["clean"] is True


def test_a_contaminated_report_suppresses_the_body(monkeypatch, capsys):
    secret = "NOT_A_REAL_PASSWORD"
    monkeypatch.setenv(DSN_ENVIRONMENT_VARIABLE, f"postgresql://u:{secret}@127.0.0.1:5432/postgres")

    # Simulate the defect this check exists to catch: a runner path that leaks
    # the credential into the report body.
    def leaky_run():
        return {"leaked": secret, "result": "PASS"}, 0

    monkeypatch.setattr("tools.postgres_foundation_proofs.runner.run", leaky_run)

    code = main([])
    out = capsys.readouterr().out

    assert code == EXIT_REPORT_CONTAMINATED
    assert secret not in out
    document = json.loads(out)
    assert document["error_category"] == "report_contaminated"
    assert "leaked" not in document
