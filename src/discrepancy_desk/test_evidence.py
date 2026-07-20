from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

EVIDENCE_PATH_ENV = "DISCREPANCY_DESK_PYTEST_EVIDENCE_PATH"


@dataclass(frozen=True)
class TestEvidenceInput:
    __test__ = False
    invariant_id: str
    fixture_id: str
    fixture_version: str
    command: str
    commit_sha: str
    sqlite_version: str
    python_version: str
    expected_result: str
    actual_result: str
    passed: bool


def write_test_evidence(
    destination: Path,
    evidence: TestEvidenceInput,
    *,
    attachments: tuple[Path, ...] = (),
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    attachment_records = []
    for attachment in sorted(attachments, key=lambda path: path.as_posix()):
        data = attachment.read_bytes()
        attachment_records.append(
            {
                "path": attachment.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_size": len(data),
            }
        )
    payload = {
        "invariant_id": evidence.invariant_id,
        "fixture_id": evidence.fixture_id,
        "fixture_version": evidence.fixture_version,
        "command": evidence.command,
        "commit_sha": evidence.commit_sha,
        "sqlite_version": evidence.sqlite_version,
        "python_version": evidence.python_version,
        "expected_result": evidence.expected_result,
        "actual_result": evidence.actual_result,
        "passed": evidence.passed,
        "attachments": attachment_records,
    }
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination


def _slug(parts: Iterable[str]) -> str:
    joined = "-".join(parts)
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", joined).strip("-.")
    return value[:120] or "session"


def pytest_evidence_destination(
    invocation_args: Iterable[str], env: Mapping[str, str] | None = None
) -> Path:
    environment = os.environ if env is None else env
    explicit = environment.get(EVIDENCE_PATH_ENV, "").strip()
    if explicit:
        return Path(explicit)
    test_targets = []
    for arg in invocation_args:
        if arg.startswith("-"):
            continue
        base = arg.split("::", 1)[0]
        candidate = Path(base)
        if "::" in arg or candidate.suffix == ".py" or candidate.exists():
            test_targets.append(arg)
    if not test_targets:
        return Path("runtime/test-evidence/full-suite.json")
    return Path("runtime/test-evidence/focused") / f"{_slug(test_targets)}.json"
