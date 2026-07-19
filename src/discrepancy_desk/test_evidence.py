from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


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
