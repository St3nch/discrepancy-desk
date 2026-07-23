from __future__ import annotations

import json
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .actor_context import ActorContext
from .parser_contract import ParserTuple, canonical_json, load_canonical_json_bytes, sha256_bytes
from .parser_worker import sanitized_worker_environment
from .srt_contract import (
    INITIAL_SRT_CONFIG,
    SRT_IMPLEMENTATION_SHA256,
    SRT_IMPLEMENTATION_VERSION,
    SRT_PACKAGE_SCHEMA_VERSION,
    SRT_PARSER_ID,
    SRT_SECURITY_PROFILE_ID,
    SRT_WARNING_POLICY_VERSION,
    SRT_WORKER_PROTOCOL_VERSION,
    assemble_srt_normalized_package,
    canonical_srt_config_bytes,
    sha256_file,
    srt_parser_tuple,
    validate_srt_candidate,
)
from .vault_persistence import append_vault_audit, request_hash, utc_now


@dataclass(frozen=True, slots=True)
class SrtResources:
    root: Path
    manifest_sha256: str
    config_sha256: str
    schema_sha256: str
    implementation_sha256: str
    dependency_lock_sha256: str

    def parser_tuple(self) -> ParserTuple:
        return srt_parser_tuple(
            resource_manifest_sha256=self.manifest_sha256,
            dependency_lock_sha256=self.dependency_lock_sha256,
            config_sha256=self.config_sha256,
        )


@dataclass(frozen=True, slots=True)
class SrtWorkerResult:
    candidate: dict[str, object] | None
    candidate_bytes: bytes | None
    receipt: dict[str, object]
    receipt_bytes: bytes
    exit_code: int


def _resource_candidates(project_root: Path | None = None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if project_root is not None:
        candidates.append(project_root / "parser_resources" / SRT_PARSER_ID)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "parser_resources" / SRT_PARSER_ID)
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "parser_resources" / SRT_PARSER_ID,
            Path(sys.executable).resolve().parent / "parser_resources" / SRT_PARSER_ID,
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def locate_srt_resources(project_root: Path | None = None) -> Path:
    for candidate in _resource_candidates(project_root):
        if (candidate / "manifest.sha256").is_file():
            return candidate
    raise FileNotFoundError("SRT parser resources are unavailable")


def _parse_manifest(path: Path) -> dict[tuple[str, str], str]:
    entries: dict[tuple[str, str], str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 3:
            raise ValueError("SRT parser manifest line is malformed")
        kind, resource_path, digest = parts
        key = (kind, resource_path)
        if key in entries:
            raise ValueError("SRT parser manifest contains a duplicate entry")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("SRT parser manifest hash is invalid")
        entries[key] = digest
    return entries


def load_srt_resources(project_root: Path | None = None) -> SrtResources:
    root = locate_srt_resources(project_root)
    manifest_path = root / "manifest.sha256"
    entries = _parse_manifest(manifest_path)
    required = {
        ("config", "config.json"),
        ("dependency-lock", "uv.lock"),
        ("implementation", "discrepancy_desk.parsers.srt_v1"),
        ("schema", "schema.json"),
    }
    if set(entries) != required:
        raise ValueError("SRT parser manifest entries diverge from the D040 set")
    config_path = root / "config.json"
    schema_path = root / "schema.json"
    config_sha = sha256_file(config_path)
    schema_sha = sha256_file(schema_path)
    if config_sha != entries[("config", "config.json")]:
        raise ValueError("SRT parser configuration hash mismatch")
    if schema_sha != entries[("schema", "schema.json")]:
        raise ValueError("SRT parser schema hash mismatch")
    config_bytes = config_path.read_bytes()
    if config_bytes != canonical_srt_config_bytes() or json.loads(config_bytes.decode("utf-8")) != INITIAL_SRT_CONFIG:
        raise ValueError("SRT parser configuration bytes are not canonical")
    implementation_sha = entries[("implementation", "discrepancy_desk.parsers.srt_v1")]
    if implementation_sha != SRT_IMPLEMENTATION_SHA256:
        raise ValueError("SRT parser implementation manifest hash mismatch")
    source_path = Path(__file__).resolve().parent / "parsers" / "srt_v1.py"
    if not source_path.is_file() or sha256_file(source_path) != implementation_sha:
        raise ValueError("SRT parser implementation bytes diverge from the manifest")
    dependency_sha = entries[("dependency-lock", "uv.lock")]
    lock_candidates = [root.parents[1] / "uv.lock", Path(sys.executable).resolve().parent / "uv.lock"]
    lock_path = next((path for path in lock_candidates if path.is_file()), None)
    if lock_path is None:
        raise FileNotFoundError("SRT dependency lock bytes are unavailable")
    if sha256_file(lock_path) != dependency_sha:
        raise ValueError("SRT dependency lock bytes diverge from the manifest")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("$id") != "urn:discrepancy-desk:m06a.normalized-package.srt.v1":
        raise ValueError("SRT parser schema identity mismatch")
    return SrtResources(
        root=root,
        manifest_sha256=sha256_file(manifest_path),
        config_sha256=config_sha,
        schema_sha256=schema_sha,
        implementation_sha256=implementation_sha,
        dependency_lock_sha256=dependency_sha,
    )


def _candidate_ids(resources: SrtResources) -> tuple[str, str, str]:
    parser_tuple = resources.parser_tuple()
    definition_material = {
        key: value for key, value in parser_tuple.material().items() if key != "config_sha256"
    }
    definition_hash = sha256_bytes(canonical_json(definition_material))
    tuple_hash = parser_tuple.sha256()
    definition_id = f"parser-definition-m06a-srt-v1-{definition_hash[:16]}"
    config_id = f"parser-config-m06a-srt-v1-{definition_hash[:12]}-{resources.config_sha256[:16]}"
    admission_id = f"parser-admission-m06a-srt-v1-under-test-{tuple_hash[:16]}"
    return definition_id, config_id, admission_id


def _pending_evidence_hash(label: str) -> str:
    return sha256_bytes(f"m06a.srt.v1:under-test:{label}:pending".encode("utf-8"))


def install_under_test_srt_candidate(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    project_root: Path | None = None,
) -> tuple[str, str, str]:
    resources = load_srt_resources(project_root)
    parser_tuple = resources.parser_tuple()
    definition_id, config_id, admission_id = _candidate_ids(resources)
    metadata = connection.execute(
        "SELECT vault_account_id FROM vault_metadata WHERE singleton_id=1"
    ).fetchone()
    if metadata is None:
        raise ValueError("Vault metadata is unavailable for SRT candidate installation")
    vault_account_id = str(metadata[0])
    actor_row = connection.execute(
        "SELECT actor_class, status, authority_profile FROM actors WHERE vault_account_id=? AND id=?",
        (vault_account_id, actor_id),
    ).fetchone()
    if actor_row is None or str(actor_row[0]) != "human" or str(actor_row[1]) != "active":
        raise PermissionError("SRT candidate installation requires the active Vault owner")
    authorities = {value.strip() for value in str(actor_row[2]).split(",") if value.strip()}
    if "vault_admin" not in authorities and "*" not in authorities:
        raise PermissionError("SRT candidate installation requires Vault administration authority")

    existing = connection.execute(
        """SELECT d.implementation_sha256, d.resource_manifest_sha256, d.dependency_lock_sha256,
                  c.config_sha256, a.state, a.dependency_lock_sha256
        FROM parser_definitions d
        JOIN parser_configuration_versions c
          ON c.vault_account_id=d.vault_account_id AND c.parser_definition_id=d.id
        JOIN parser_admission_versions a
          ON a.vault_account_id=d.vault_account_id
         AND a.parser_definition_id=d.id
         AND a.parser_configuration_version_id=c.id
        WHERE d.vault_account_id=? AND d.id=? AND c.id=? AND a.id=?""",
        (vault_account_id, definition_id, config_id, admission_id),
    ).fetchone()
    if existing is not None:
        expected = (
            parser_tuple.implementation_sha256,
            parser_tuple.resource_manifest_sha256,
            parser_tuple.dependency_lock_sha256,
            parser_tuple.config_sha256,
            "under_test",
            parser_tuple.dependency_lock_sha256,
        )
        if tuple(str(value) for value in existing) != expected:
            raise ValueError("installed SRT candidate tuple conflicts with packaged resources")
        return definition_id, config_id, admission_id
    if connection.execute(
        "SELECT 1 FROM parser_definitions WHERE vault_account_id=? AND id=?",
        (vault_account_id, definition_id),
    ).fetchone() is not None:
        raise ValueError("SRT parser definition exists with an unrecognized tuple")

    created_at = utc_now()
    actor = ActorContext(
        actor_id=actor_id,
        actor_class="human",
        vault_account_id=vault_account_id,
        correlation_id=f"install:{admission_id}",
        authentication_source="governed-srt-parser-installation",
        allowed_operation_class="vault_admin",
    )
    request_sha256 = request_hash(
        {"admission_id": admission_id, "state": "under_test", **parser_tuple.material()}
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """INSERT INTO parser_definitions
            (id, vault_account_id, format_id, implementation_kind, implementation_entrypoint,
             implementation_version, implementation_sha256, resource_manifest_sha256,
             dependency_lock_sha256, license_id, package_schema_version,
             deterministic_contract_version, security_profile_id, created_at, created_by_actor_id)
            VALUES (?, ?, 'application/x-subrip', 'internal',
                    'discrepancy_desk.parsers.srt_v1:parse_bytes', ?, ?, ?, ?,
                    'project-code', ?, ?, ?, ?, ?)""",
            (
                definition_id,
                vault_account_id,
                SRT_IMPLEMENTATION_VERSION,
                parser_tuple.implementation_sha256,
                parser_tuple.resource_manifest_sha256,
                parser_tuple.dependency_lock_sha256,
                SRT_PACKAGE_SCHEMA_VERSION,
                parser_tuple.deterministic_contract_version,
                SRT_SECURITY_PROFILE_ID,
                created_at,
                actor_id,
            ),
        )
        connection.execute(
            """INSERT INTO parser_configuration_versions
            (id, vault_account_id, parser_definition_id, canonical_config_json, config_sha256,
             size_limit_bytes, depth_limit, element_limit, line_limit, maximum_line_bytes,
             warning_policy_version, created_at, created_by_actor_id)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
            (
                config_id,
                vault_account_id,
                definition_id,
                canonical_srt_config_bytes(),
                parser_tuple.config_sha256,
                int(INITIAL_SRT_CONFIG["input_size_limit_bytes"]),
                int(INITIAL_SRT_CONFIG["cue_limit"]),
                int(INITIAL_SRT_CONFIG["line_limit"]),
                int(INITIAL_SRT_CONFIG["maximum_cue_bytes"]),
                SRT_WARNING_POLICY_VERSION,
                created_at,
                actor_id,
            ),
        )
        connection.execute(
            """INSERT INTO parser_admission_versions
            (id, vault_account_id, parser_definition_id, parser_configuration_version_id,
             state, fixture_manifest_sha256, focused_test_evidence_sha256,
             no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
             dependency_lock_sha256, admitted_by_actor_id, admitted_at,
             supersedes_admission_id, reason, created_at, created_by_actor_id)
            VALUES (?, ?, ?, ?, 'under_test', ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)""",
            (
                admission_id,
                vault_account_id,
                definition_id,
                config_id,
                _pending_evidence_hash("fixtures"),
                _pending_evidence_hash("focused-tests"),
                _pending_evidence_hash("no-egress"),
                _pending_evidence_hash("packaged-sidecar"),
                parser_tuple.dependency_lock_sha256,
                "D040 SRT candidate; owner admission and canonical execution are blocked",
                created_at,
                actor_id,
            ),
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="parser_admission_version",
            record_id=admission_id,
            payload={
                "parser_definition_id": definition_id,
                "parser_configuration_version_id": config_id,
                "state": "under_test",
                "canonical_available": False,
            },
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return definition_id, config_id, admission_id


def list_srt_status(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    project_root: Path | None = None,
) -> dict[str, object]:
    resources = load_srt_resources(project_root)
    definition_id, config_id, admission_id = _candidate_ids(resources)
    row = connection.execute(
        """SELECT a.state
        FROM parser_definitions d
        JOIN parser_configuration_versions c
          ON c.vault_account_id=d.vault_account_id AND c.parser_definition_id=d.id
        JOIN parser_admission_versions a
          ON a.vault_account_id=d.vault_account_id
         AND a.parser_definition_id=d.id
         AND a.parser_configuration_version_id=c.id
        WHERE d.vault_account_id=? AND d.id=? AND c.id=? AND a.id=?""",
        (vault_account_id, definition_id, config_id, admission_id),
    ).fetchone()
    state = str(row[0]) if row is not None else "not_installed"
    return {
        "parser_definition_id": definition_id,
        "parser_configuration_version_id": config_id,
        "parser_admission_version_id": admission_id if row is not None else None,
        "parser_id": SRT_PARSER_ID,
        "display_name": "SubRip (SRT)",
        "state": state,
        "canonical_available": False,
        "admission_ready": False,
        "admission_manifest": None,
        "reason_code": "owner_admission_not_authorized" if row is not None else "candidate_not_installed",
        "package_schema_version": SRT_PACKAGE_SCHEMA_VERSION,
        "security_profile_id": SRT_SECURITY_PROFILE_ID,
    }


def list_all_parser_status(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    project_root: Path | None = None,
) -> list[dict[str, object]]:
    from .parser_service import list_parser_status

    return list_parser_status(
        connection, vault_account_id=vault_account_id, project_root=project_root
    ) + [
        list_srt_status(
            connection, vault_account_id=vault_account_id, project_root=project_root
        )
    ]


def run_under_test_srt_worker(
    input_bytes: bytes,
    *,
    operation_parent: Path | None = None,
    project_root: Path | None = None,
    timeout_seconds: int = 30,
) -> SrtWorkerResult:
    resources = load_srt_resources(project_root)
    parent = operation_parent or Path(tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    operation_root = Path(tempfile.mkdtemp(prefix="m06a-srt-parser-", dir=parent))
    try:
        input_path = operation_root / "verified-input.bin"
        with input_path.open("xb") as handle:
            handle.write(input_bytes)
            handle.flush()
        request = {
            "config_sha256": resources.config_sha256,
            "implementation_sha256": resources.implementation_sha256,
            "output_filename": "candidate-package.json",
            "parser_id": SRT_PARSER_ID,
            "protocol_version": SRT_WORKER_PROTOCOL_VERSION,
            "security_profile_id": SRT_SECURITY_PROFILE_ID,
            "verified_input_relative_name": "verified-input.bin",
            "verified_input_sha256": sha256_bytes(input_bytes),
            "verified_input_size": len(input_bytes),
        }
        request_bytes = canonical_json(request)
        framed = struct.pack(">Q", len(request_bytes)) + request_bytes
        worker_command = (
            [sys.executable, "--m06a-srt-parser-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-I", "-m", "discrepancy_desk.srt_worker"]
        )
        completed = subprocess.run(
            worker_command,
            cwd=operation_root,
            input=framed,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=sanitized_worker_environment(),
        )
        receipt_path = operation_root / "worker-receipt.json"
        if not receipt_path.is_file():
            raise RuntimeError("SRT parser worker did not preserve a receipt")
        receipt_bytes = receipt_path.read_bytes()
        receipt = load_canonical_json_bytes(receipt_bytes)
        if not isinstance(receipt, dict):
            raise RuntimeError("SRT parser worker receipt is malformed")
        candidate_path = operation_root / "candidate-package.json"
        candidate_bytes: bytes | None = None
        candidate: dict[str, object] | None = None
        if candidate_path.is_file():
            candidate_bytes = candidate_path.read_bytes()
            loaded = load_canonical_json_bytes(candidate_bytes)
            candidate = validate_srt_candidate(loaded, input_bytes=input_bytes)
            if receipt.get("candidate_package_sha256") != sha256_bytes(candidate_bytes):
                raise RuntimeError("SRT worker receipt does not match candidate bytes")
        if completed.returncode == 0 and candidate is None:
            raise RuntimeError("successful SRT worker omitted candidate output")
        if completed.returncode != 0 and candidate is not None:
            raise RuntimeError("failed SRT worker emitted candidate output")
        return SrtWorkerResult(
            candidate=candidate,
            candidate_bytes=candidate_bytes,
            receipt=receipt,
            receipt_bytes=receipt_bytes,
            exit_code=completed.returncode,
        )
    finally:
        shutil.rmtree(operation_root, ignore_errors=True)


def assemble_under_test_srt_package(
    input_bytes: bytes,
    *,
    vault_account_id: str,
    source_artifact_sha256: str,
    parser_admission_id: str,
    project_root: Path | None = None,
) -> tuple[dict[str, object], bytes, SrtWorkerResult]:
    resources = load_srt_resources(project_root)
    result = run_under_test_srt_worker(input_bytes, project_root=project_root)
    if result.exit_code != 0 or result.candidate is None:
        raise ValueError(str(result.receipt.get("terminal_outcome", "internal_error")))
    package, rendered = assemble_srt_normalized_package(
        candidate=result.candidate,
        input_bytes=input_bytes,
        vault_account_id=vault_account_id,
        source_artifact_sha256=source_artifact_sha256,
        parser_tuple=resources.parser_tuple(),
        parser_admission_id=parser_admission_id,
    )
    return package, rendered, result
