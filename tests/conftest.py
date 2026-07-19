from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def pytest_sessionfinish(session, exitstatus: int) -> None:
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    stats = reporter.stats if reporter is not None else {}
    counts = {
        name: len(stats.get(name, []))
        for name in ("passed", "failed", "skipped", "error", "xfailed", "xpassed")
    }
    payload = {
        "command": "uv run pytest",
        "commit_sha": _git_sha(),
        "python_version": sys.version.split()[0],
        "sqlite_version": sqlite3.sqlite_version,
        "exit_status": exitstatus,
        "counts": counts,
    }
    destination = Path("runtime/test-evidence/latest-pytest-session.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
