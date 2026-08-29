"""Orchestration: preflight, three isolated proofs, teardown, one JSON report.

Exit-code precedence, most serious first:

``4`` report contaminated -- a credential reached the rendered report;
``3`` cleanup failed -- proof state may remain on the substrate;
``2`` precondition failed -- nothing was proved;
``1`` a proof failed;
``5`` internal error;
``0`` all three proofs and all teardown checks passed.

A failed teardown outranks a passing proof because harness section 1.1 rule 10
is explicit that failed teardown is visible cleanup debt and never permission to
reuse unknown state.
"""

from __future__ import annotations

import contextlib
import platform
import sys
from typing import Any

import psycopg

from . import __version__, preflight, report
from .databases import (
    ProofDatabaseRegistry,
    assert_database_empty,
    assert_role_can_manage_databases,
    close_connections,
    connect,
    create_proof_database,
    drop_proof_database,
)
from .dsn import DSN_ENVIRONMENT_VARIABLE, SafeDsn, dsn_from_environment
from .errors import ErrorCategory, ProofRunError
from .evidence import Outcome, ProofResult
from .naming import new_token, proof_database_name
from .proof_a import evaluate_proof_a, run_proof_a
from .proof_b import evaluate_proof_b, run_proof_b
from .proof_c import evaluate_proof_c, run_proof_c

EXIT_OK = 0
EXIT_PROOF_FAILED = 1
EXIT_PRECONDITION_FAILED = 2
EXIT_CLEANUP_FAILED = 3
EXIT_REPORT_CONTAMINATED = 4
EXIT_INTERNAL_ERROR = 5

#: The exact argv the external VedaOps task `postgres-foundation-proofs` is
#: bound to. The two flags belong to `uv` and are environment policy, not proof
#: inputs: the task itself still takes no caller flags of any kind.
FIXED_ARGV = [
    "uv",
    "run",
    "--offline",
    "--no-sync",
    "python",
    "-m",
    "tools.postgres_foundation_proofs",
]

_PROOFS = (
    ("A", "admission ordering under concurrency", run_proof_a, evaluate_proof_a),
    ("B", "identity conflict and historical boundary", run_proof_b, evaluate_proof_b),
    ("C", "typed forward/reverse provenance", run_proof_c, evaluate_proof_c),
)


def _runner_metadata() -> dict[str, Any]:
    return {
        "package_version": __version__,
        "python_version": platform.python_version(),
        "psycopg_version": psycopg.__version__,
        "fixed_argv": FIXED_ARGV,
        "argv_contract": {
            "executable": (
                "`uv` is the bare executable required by VedaOps task policy; it is "
                "resolved from the task environment, not from a path this repository pins."
            ),
            "offline": "`--offline` forbids network access for the duration of the task.",
            "no_sync": ("`--no-sync` forbids runtime environment synchronization or provisioning."),
            "provisioning": (
                "Dependencies must already have been provisioned before commissioning. "
                "The task neither resolves nor installs dependencies during the proof, and "
                "the runner has no fallback that could."
            ),
            "working_directory": (
                "The repository root remains the working directory, which is what makes "
                "`-m tools.postgres_foundation_proofs` resolve."
            ),
            "dsn": (
                f"The DSN is read only from {DSN_ENVIRONMENT_VARIABLE} and never appears in argv."
            ),
            "caller_inputs": (
                "The task accepts no caller flags and no alternate DSN, host, port, image, "
                "relaxation, skip, or report-path inputs."
            ),
        },
        "docker": "The runner does not start or inspect Docker.",
    }


def apply_close_failure_precedence(result: ProofResult) -> None:
    """Record a close failure as the proof's failure only if nothing else is.

    A close failure is cleanup debt in its own right and always forces a
    non-zero result (via ``ProofResult.outcome``), but it must never overwrite
    an already-recorded primary failure: the original cause stays the reported
    one, with the close failures listed alongside as evidence.
    """
    if not result.close_failures:
        return
    if result.failure_category is not None:
        return
    result.failure_category = str(ErrorCategory.CONNECTION_CLOSE_FAILED)
    result.failure_message = (
        f"proof {result.proof} could not explicitly close "
        f"{len(result.close_failures)} runner-owned connection(s); "
        "DROP DATABASE ... WITH (FORCE) is a backstop, not a substitute"
    )


def _run_one_proof(
    key: str,
    title: str,
    run_fn: Any,
    evaluate_fn: Any,
    dsn: SafeDsn,
    maintenance: psycopg.Connection,
    registry: ProofDatabaseRegistry,
) -> ProofResult:
    """Create a database, run one proof, and drop the database either way."""
    result = ProofResult(proof=key, title=title)

    def connect_fn(dbname: str, application_name: str, autocommit: bool) -> psycopg.Connection:
        return connect(dsn, dbname=dbname, application_name=application_name, autocommit=autocommit)

    database: str | None = None
    try:
        # Created immediately before its proof, never all three up front.
        database = proof_database_name(key.lower(), new_token())
        create_proof_database(maintenance, database)
        registry.register(database)
        result.database = database

        # Preflight is repeated inside every proof database, and the numeric
        # major-18 gate applies to every connection used as proof evidence.
        probe = connect_fn(database, f"fnd_pg01_preflight_{key.lower()}", True)
        try:
            result.preflight = preflight.capture_preflight(
                probe, context=f"proof database {database}"
            )
            result.preflight["non_system_relations_before_setup"] = assert_database_empty(
                probe, database
            )
        finally:
            # The probe is a runner-owned connection to the proof database, so
            # it goes through the same recorded-close contract as the proof
            # sessions rather than being closed silently.
            result.connection_closures.extend(close_connections([("preflight_probe", probe)]))

        if result.close_failures:
            # Setup did not complete cleanly. Entering the substantive proof
            # now would run it alongside a connection the runner could not
            # release, and FORCE would later mask that during teardown.
            raise ProofRunError(
                ErrorCategory.CONNECTION_CLOSE_FAILED,
                f"proof {key} could not explicitly close its preflight probe connection "
                "to the proof database; setup is not clean, so the proof was not run",
            )

        observations = run_fn(connect_fn, database, result)
        result.assertions = evaluate_fn(observations)
        result.preflight["observations"] = observations.to_json()
    except ProofRunError as exc:
        result.failure_category = str(exc.category)
        result.failure_message = exc.message
    except psycopg.Error as exc:
        result.failure_category = str(ErrorCategory.PROOF_STEP_UNEXPECTED)
        result.failure_message = (
            f"proof {key} raised an unexpected database error "
            f"(sqlstate={getattr(exc, 'sqlstate', None)})"
        )
    except Exception:  # noqa: BLE001 - never let an unexpected error skip teardown
        result.failure_category = str(ErrorCategory.INTERNAL_ERROR)
        result.failure_message = f"proof {key} raised an unexpected runner error"
    finally:
        apply_close_failure_precedence(result)
        if database is not None:
            result.teardown = registry.drop(database)
    return result


def run() -> tuple[dict[str, Any], int]:
    """Execute the full proof session and return ``(document, exit_code)``."""
    document: dict[str, Any] = {
        "report_version": report.REPORT_VERSION,
        "ticket": "FND-PG01",
        "governing_documents": [
            "docs/tickets/FND-PG01-postgresql-foundation-proofs.md",
            "docs/tickets/FND-PG01-steward-reconciliation-01.md",
            "docs/design/POSTGRESQL-SCRATCH-PROOF-HARNESS-01.md",
        ],
        "runner": _runner_metadata(),
        "evidence_responsibility": report.evidence_responsibility(),
    }

    # -- Preconditions. Nothing is created until all of these pass. -----------
    try:
        dsn = dsn_from_environment()
        document["connection"] = dsn.observation()

        maintenance = connect(dsn, autocommit=True, application_name="fnd_pg01_maintenance")
    except ProofRunError as exc:
        document["result"] = str(Outcome.FAIL)
        document["error_category"] = str(exc.category)
        document["error_message"] = exc.message
        document["human_summary"] = (
            f"FND-PG01 refused to start: {exc.message}. No proof database was created."
        )
        return document, EXIT_PRECONDITION_FAILED

    proofs: list[ProofResult] = []
    registry = ProofDatabaseRegistry(lambda name: drop_proof_database(maintenance, name))
    try:
        try:
            document["preflight_maintenance"] = preflight.capture_preflight(
                maintenance, context=f"maintenance connection {dsn.redacted()}"
            )
            document["role_capability"] = assert_role_can_manage_databases(
                maintenance, context=dsn.redacted()
            )
        except ProofRunError as exc:
            document["result"] = str(Outcome.FAIL)
            document["error_category"] = str(exc.category)
            document["error_message"] = exc.message
            document["human_summary"] = (
                f"FND-PG01 refused to proceed: {exc.message}. No proof database was created."
            )
            return document, EXIT_PRECONDITION_FAILED

        for key, title, run_fn, evaluate_fn in _PROOFS:
            proofs.append(
                _run_one_proof(key, title, run_fn, evaluate_fn, dsn, maintenance, registry)
            )
    finally:
        # Process-level backstop for anything a proof-local finally missed.
        registry.sweep()
        # A close failure must not mask the real proof result.
        with contextlib.suppress(Exception):
            maintenance.close()

    outcomes = {p.proof: p.outcome for p in proofs}
    close_failures = [failure for p in proofs for failure in p.close_failures]
    teardown_ok = registry.all_dropped and not close_failures
    all_passed = bool(proofs) and all(o is Outcome.PASS for o in outcomes.values())
    overall = Outcome.PASS if (all_passed and teardown_ok) else Outcome.FAIL

    document["proofs"] = [p.to_json() for p in proofs]
    document["teardown"] = {
        "results": registry.results,
        "all_databases_dropped": registry.all_dropped,
        "connection_close_failures": close_failures,
        "all_dropped": teardown_ok,
        "outstanding": list(registry.outstanding),
        "failures": registry.failures,
        "note": (
            "A failed teardown is visible cleanup debt and never permission to reuse unknown state."
        ),
    }
    document["foundation_item_consequences"] = report.foundation_consequences(outcomes)
    document["production_schema_statement"] = (
        "No production Desk database or schema, migration, or 0001_initial was created. "
        "All objects lived under schema 'proof' inside uniquely named disposable proof "
        "databases, each force-dropped after its proof."
    )
    document["result"] = str(overall)
    document["human_summary"] = report.build_human_summary(overall, proofs, teardown_ok)

    if not teardown_ok:
        return document, EXIT_CLEANUP_FAILED
    if overall is Outcome.FAIL:
        return document, EXIT_PROOF_FAILED
    return document, EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Entry point. Flagless by contract; emits one JSON document to stdout."""
    args = sys.argv[1:] if argv is None else argv
    if args:
        document = {
            "report_version": report.REPORT_VERSION,
            "ticket": "FND-PG01",
            "result": str(Outcome.FAIL),
            "error_category": str(ErrorCategory.INTERNAL_ERROR),
            "error_message": (
                "the governed proof task accepts no command-line arguments; "
                "the DSN is supplied only through "
                f"{DSN_ENVIRONMENT_VARIABLE}"
            ),
            "human_summary": (
                "FND-PG01 refused to start: unexpected command-line arguments. The task is "
                "flagless by contract."
            ),
        }
        print(report.render(document))
        return EXIT_PRECONDITION_FAILED

    secret_candidates: frozenset[str] = frozenset()
    try:
        dsn_for_scrub = dsn_from_environment()
    except ProofRunError:
        dsn_for_scrub = None
    if dsn_for_scrub is not None:
        secret_candidates = dsn_for_scrub.secret_candidates()

    try:
        document, exit_code = run()
    except Exception:  # noqa: BLE001 - never emit a raw traceback; it can carry the DSN
        document = {
            "report_version": report.REPORT_VERSION,
            "ticket": "FND-PG01",
            "result": str(Outcome.FAIL),
            "error_category": str(ErrorCategory.INTERNAL_ERROR),
            "error_message": "the runner raised an unhandled internal error",
            "human_summary": "FND-PG01 failed with an unhandled internal runner error.",
        }
        exit_code = EXIT_INTERNAL_ERROR

    try:
        # Scan the body, record the scan result, then re-scan the *final*
        # rendering so the string that is verified is byte-identical to the
        # string that is printed.
        document["secret_scan"] = report.scan_for_secrets(
            report.render(document), secret_candidates
        )
        rendered = report.render(document)
        scan = report.scan_for_secrets(rendered, secret_candidates)
    except Exception:  # noqa: BLE001 - a raw traceback could carry report content
        print(
            report.render(
                {
                    "report_version": report.REPORT_VERSION,
                    "ticket": "FND-PG01",
                    "result": str(Outcome.FAIL),
                    "error_category": str(ErrorCategory.INTERNAL_ERROR),
                    "error_message": "the runner could not render its report",
                    "human_summary": (
                        "FND-PG01 report could not be rendered. No report body is emitted."
                    ),
                }
            )
        )
        return EXIT_INTERNAL_ERROR

    if not scan["clean"]:
        print(report.render(report.contaminated_document(scan)))
        return EXIT_REPORT_CONTAMINATED

    print(rendered)
    return exit_code
