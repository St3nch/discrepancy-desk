from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from discrepancy_desk.db import connect_existing
from discrepancy_desk.migration_runner import run_guarded_upgrade
from discrepancy_desk.migration_spec import central_migration_spec, vault_migration_spec
from discrepancy_desk.test_evidence import pytest_evidence_destination as evidence_destination


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _working_tree_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    return bool(completed.stdout.strip()) if completed.returncode == 0 else True


def pytest_sessionfinish(session, exitstatus: int) -> None:
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    stats = reporter.stats if reporter is not None else {}
    counts = {
        name: len(stats.get(name, []))
        for name in ("passed", "failed", "skipped", "error", "xfailed", "xpassed")
    }
    destination = evidence_destination(session.config.invocation_params.args)
    payload = {
        "command": "uv run pytest",
        "commit_sha": _git_sha(),
        "working_tree_dirty": _working_tree_dirty(),
        "invariant_id": destination.stem if destination.name != "latest-full-suite.json" else None,
        "python_version": sys.version.split()[0],
        "sqlite_version": sqlite3.sqlite_version,
        "exit_status": exitstatus,
        "counts": counts,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


@pytest.fixture
def m06a_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def m06a_central_spec(m06a_project_root: Path):
    return central_migration_spec(m06a_project_root)


@pytest.fixture
def m06a_vault_spec(m06a_project_root: Path):
    return vault_migration_spec(m06a_project_root)


@pytest.fixture
def m06a_central_connection(tmp_path: Path, m06a_central_spec):
    database_path = tmp_path / "central.sqlite3"
    run_guarded_upgrade(
        database_path,
        m06a_central_spec,
        operation_id="fixture-central-migration",
        allow_create=True,
    )
    connection = connect_existing(database_path)
    try:
        yield connection, database_path
    finally:
        connection.close()
