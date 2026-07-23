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
from .parser_contract import (
    INITIAL_TEXT_CONFIG,
    PACKAGE_SCHEMA_VERSION,
    PARSER_ID,
    PARSER_IMPLEMENTATION_SHA256,
    PARSER_IMPLEMENTATION_VERSION,
    SECURITY_PROFILE_ID,
    WORKER_PROTOCOL_VERSION,
    ParserTuple,
    assemble_normalized_package,
    canonical_config_bytes,
    canonical_json,
    load_canonical_json_bytes,
    require_sha256,
    sha256_bytes,
    sha256_file,
    validate_candidate_core,
)
from .vault_persistence import append_vault_audit, request_hash, utc_now


@dataclass(frozen=True, slots=True)
class ParserResources:
    root: Path
    manifest_sha256: str
    config_sha256: str
    schema_sha256: str
    implementation_sha256: str
    dependency_lock_sha256: str

    def parser_tuple(self) -> ParserTuple:
        return ParserTuple(
            parser_id=PARSER_ID,
            implementation_version=PARSER_IMPLEMENTATION_VERSION,
            implementation_sha256=self.implementation_sha256,
            resource_manifest_sha256=self.manifest_sha256,
            dependency_lock_sha256=self.dependency_lock_sha256,
            config_sha256=self.config_sha256,
        )


@dataclass(frozen=True, slots=True)
class WorkerResult:
    candidate: dict[str, object] | None
    candidate_bytes: bytes | None
    receipt: dict[str, object]
    receipt_bytes: bytes
    exit_code: int


@dataclass(frozen=True, slots=True)
class CanonicalParserSelection:
    parser_definition_id: str
    parser_configuration_version_id: str
    parser_admission_version_id: str
    artifact_sha256: str
    artifact_size: int
    artifact_relative_path: str
    parser_tuple: ParserTuple


def _resource_candidates(project_root: Path | None = None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if project_root is not None:
        candidates.append(project_root / "parser_resources")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "parser_resources")
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "parser_resources",
            Path(sys.executable).resolve().parent / "parser_resources",
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def locate_parser_resources(project_root: Path | None = None) -> Path:
    for candidate in _resource_candidates(project_root):
        if (candidate / "manifest.sha256").is_file():
            return candidate
    raise FileNotFoundError("parser resources are unavailable")


def _parse_manifest(path: Path) -> dict[tuple[str, str], str]:
    entries: dict[tuple[str, str], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(" ")
        if len(parts) != 3:
            raise ValueError("parser resource manifest is malformed")
        kind, name, digest = parts
        require_sha256(digest, label="parser resource manifest hash")
        key = (kind, name)
        if key in entries:
            raise ValueError("parser resource manifest contains a duplicate entry")
        entries[key] = digest
    return entries


def load_parser_resources(project_root: Path | None = None) -> ParserResources:
    root = locate_parser_resources(project_root)
    manifest_path = root / "manifest.sha256"
    entries = _parse_manifest(manifest_path)
    required = {
        ("config", "configs/m06a.text.v1.json"),
        ("schema", "schemas/m06a.normalized-package.v1.json"),
        ("implementation", "discrepancy_desk.parsers.plain_text_v1"),
        ("dependency-lock", "uv.lock"),
    }
    if set(entries) != required:
        raise ValueError("parser resource manifest entries diverge from the admitted set")
    config_path = root / "configs" / "m06a.text.v1.json"
    schema_path = root / "schemas" / "m06a.normalized-package.v1.json"
    config_sha = sha256_file(config_path)
    schema_sha = sha256_file(schema_path)
    if config_sha != entries[("config", "configs/m06a.text.v1.json")]:
        raise ValueError("parser configuration hash mismatch")
    if schema_sha != entries[("schema", "schemas/m06a.normalized-package.v1.json")]:
        raise ValueError("parser schema hash mismatch")
    config_bytes = config_path.read_bytes()
    if config_bytes != canonical_config_bytes() or json.loads(config_bytes.decode("utf-8")) != INITIAL_TEXT_CONFIG:
        raise ValueError("parser configuration bytes are not canonical")
    implementation_sha = entries[("implementation", "discrepancy_desk.parsers.plain_text_v1")]
    if implementation_sha != PARSER_IMPLEMENTATION_SHA256:
        raise ValueError("parser implementation manifest hash mismatch")
    source_path = Path(__file__).resolve().parent / "parsers" / "plain_text_v1.py"
    if source_path.is_file() and sha256_file(source_path) != implementation_sha:
        raise ValueError("parser implementation bytes diverge from the admitted hash")
    dependency_sha = entries[("dependency-lock", "uv.lock")]
    lock_candidates = [root.parent / "uv.lock", Path(sys.executable).resolve().parent / "uv.lock"]
    existing_lock = next((path for path in lock_candidates if path.is_file()), None)
    if existing_lock is not None and sha256_file(existing_lock) != dependency_sha:
        raise ValueError("dependency lock bytes diverge from the admitted hash")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("$id") != "urn:discrepancy-desk:m06a.normalized-package.v1":
        raise ValueError("parser schema identity mismatch")
    return ParserResources(
        root=root,
        manifest_sha256=sha256_file(manifest_path),
        config_sha256=config_sha,
        schema_sha256=schema_sha,
        implementation_sha256=implementation_sha,
        dependency_lock_sha256=dependency_sha,
    )


def _pending_evidence_hash(label: str) -> str:
    return sha256_bytes(f"m06a.text.v1:under-test:{label}:pending".encode("utf-8"))


def _candidate_ids(resources: ParserResources) -> tuple[str, str, str]:
    tuple_hash = resources.parser_tuple().sha256()
    definition_id = "parser-definition-m06a-text-v1"
    config_id = f"parser-config-m06a-text-v1-{resources.config_sha256[:16]}"
    admission_id = f"parser-admission-m06a-text-v1-under-test-{tuple_hash[:16]}"
    return definition_id, config_id, admission_id


def install_under_test_parser_candidate(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    project_root: Path | None = None,
) -> tuple[str, str, str]:
    resources = load_parser_resources(project_root)
    parser_tuple = resources.parser_tuple()
    definition_id, config_id, admission_id = _candidate_ids(resources)
    metadata = connection.execute(
        "SELECT vault_account_id FROM vault_metadata WHERE singleton_id=1"
    ).fetchone()
    if metadata is None:
        raise ValueError("Vault metadata is unavailable for parser installation")
    vault_account_id = str(metadata[0])
    actor_row = connection.execute(
        "SELECT actor_class, status, authority_profile FROM actors WHERE vault_account_id=? AND id=?",
        (vault_account_id, actor_id),
    ).fetchone()
    if actor_row is None or str(actor_row[0]) != "human" or str(actor_row[1]) != "active":
        raise PermissionError("parser candidate installation requires the active Vault owner")
    authorities = {value.strip() for value in str(actor_row[2]).split(",") if value.strip()}
    if "vault_admin" not in authorities and "*" not in authorities:
        raise PermissionError("parser candidate installation requires Vault administration authority")

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
            raise ValueError("installed parser candidate tuple conflicts with packaged resources")
        return definition_id, config_id, admission_id

    if connection.execute(
        "SELECT 1 FROM parser_definitions WHERE vault_account_id=? AND id=?",
        (vault_account_id, definition_id),
    ).fetchone() is not None:
        raise ValueError("parser definition exists with an unrecognized tuple")

    created_at = utc_now()
    actor = ActorContext(
        actor_id=actor_id,
        actor_class="human",
        vault_account_id=vault_account_id,
        correlation_id=f"install:{admission_id}",
        authentication_source="governed-parser-installation",
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
            VALUES (?, ?, 'text/plain', 'internal', 'discrepancy_desk.parsers.plain_text_v1:parse_bytes',
                    ?, ?, ?, ?, 'project-code', ?, ?, ?, ?, ?)""",
            (
                definition_id,
                vault_account_id,
                parser_tuple.implementation_version,
                parser_tuple.implementation_sha256,
                parser_tuple.resource_manifest_sha256,
                parser_tuple.dependency_lock_sha256,
                parser_tuple.package_schema_version,
                parser_tuple.deterministic_contract_version,
                parser_tuple.security_profile_id,
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
                canonical_config_bytes(),
                parser_tuple.config_sha256,
                int(INITIAL_TEXT_CONFIG["input_size_limit_bytes"]),
                int(INITIAL_TEXT_CONFIG["element_limit"]),
                int(INITIAL_TEXT_CONFIG["line_limit"]),
                int(INITIAL_TEXT_CONFIG["maximum_line_bytes"]),
                str(INITIAL_TEXT_CONFIG["warning_policy_version"]),
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
                "D036 under-test candidate; owner admission is separately blocked",
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


def list_parser_status(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    project_root: Path | None = None,
) -> list[dict[str, object]]:
    resources = load_parser_resources(project_root)
    rows = connection.execute(
        """SELECT d.id, d.format_id, d.package_schema_version, d.security_profile_id,
                  d.implementation_sha256, d.resource_manifest_sha256, d.dependency_lock_sha256,
                  c.id, c.config_sha256, a.id, a.state
        FROM parser_definitions d
        JOIN parser_configuration_versions c
          ON c.vault_account_id=d.vault_account_id AND c.parser_definition_id=d.id
        JOIN parser_admission_versions a
          ON a.vault_account_id=d.vault_account_id
         AND a.parser_definition_id=d.id
         AND a.parser_configuration_version_id=c.id
        WHERE d.vault_account_id=?
          AND NOT EXISTS (
              SELECT 1 FROM parser_admission_versions successor
              WHERE successor.vault_account_id=a.vault_account_id
                AND successor.supersedes_admission_id=a.id
          )
        ORDER BY d.id, a.created_at, a.id""",
        (vault_account_id,),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row[0]), []).append(row)
    result: list[dict[str, object]] = []
    for definition_id, current in grouped.items():
        if len(current) != 1:
            result.append(
                {
                    "parser_definition_id": definition_id,
                    "parser_id": PARSER_ID,
                    "display_name": "Plain Text",
                    "state": "unavailable",
                    "canonical_available": False,
                    "reason_code": "ambiguous_current_admission",
                    "package_schema_version": PACKAGE_SCHEMA_VERSION,
                    "security_profile_id": SECURITY_PROFILE_ID,
                }
            )
            continue
        row = current[0]
        tuple_matches = (
            str(row[4]) == resources.implementation_sha256
            and str(row[5]) == resources.manifest_sha256
            and str(row[6]) == resources.dependency_lock_sha256
            and str(row[8]) == resources.config_sha256
            and str(row[2]) == PACKAGE_SCHEMA_VERSION
            and str(row[3]) == SECURITY_PROFILE_ID
        )
        state = str(row[10])
        result.append(
            {
                "parser_definition_id": definition_id,
                "parser_configuration_version_id": str(row[7]),
                "parser_admission_version_id": str(row[9]),
                "parser_id": PARSER_ID,
                "display_name": "Plain Text",
                "format_id": str(row[1]),
                "state": state if tuple_matches else "unavailable",
                "canonical_available": bool(tuple_matches and state == "owner_admitted"),
                "reason_code": (
                    None
                    if tuple_matches and state == "owner_admitted"
                    else "not_owner_admitted"
                    if tuple_matches
                    else "packaged_tuple_mismatch"
                ),
                "package_schema_version": str(row[2]),
                "security_profile_id": str(row[3]),
            }
        )
    return result


def resolve_canonical_parser(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    acquisition_artifact_link_id: str,
    project_root: Path | None = None,
) -> CanonicalParserSelection:
    resources = load_parser_resources(project_root)
    artifact = connection.execute(
        """SELECT ao.sha256, ao.byte_size, ao.storage_relative_path,
                  rr.retention_eligible, acq.outcome
        FROM acquisition_artifact_links link
        JOIN artifact_objects ao
          ON ao.vault_account_id=link.vault_account_id AND ao.id=link.artifact_object_id
        JOIN acquisitions acq
          ON acq.vault_account_id=link.vault_account_id AND acq.id=link.acquisition_id
        JOIN rights_retention_versions rr
          ON rr.vault_account_id=link.vault_account_id
         AND rr.id=link.rights_retention_version_id
        WHERE link.vault_account_id=? AND link.id=?""",
        (vault_account_id, acquisition_artifact_link_id),
    ).fetchone()
    if artifact is None:
        raise ValueError("canonical parser input is not a same-Vault artifact link")
    if str(artifact[3]) != "allow" or str(artifact[4]) != "succeeded":
        raise PermissionError("canonical parser input is not preservation-compatible")
    status = list_parser_status(
        connection, vault_account_id=vault_account_id, project_root=project_root
    )
    eligible = [row for row in status if row["parser_id"] == PARSER_ID]
    if len(eligible) != 1 or not eligible[0]["canonical_available"]:
        raise PermissionError("no owner-admitted parser is available for canonical use")
    row = eligible[0]
    return CanonicalParserSelection(
        parser_definition_id=str(row["parser_definition_id"]),
        parser_configuration_version_id=str(row["parser_configuration_version_id"]),
        parser_admission_version_id=str(row["parser_admission_version_id"]),
        artifact_sha256=str(artifact[0]),
        artifact_size=int(artifact[1]),
        artifact_relative_path=str(artifact[2]),
        parser_tuple=resources.parser_tuple(),
    )


def run_under_test_worker(
    input_bytes: bytes,
    *,
    operation_parent: Path | None = None,
    project_root: Path | None = None,
    timeout_seconds: int = 30,
) -> WorkerResult:
    resources = load_parser_resources(project_root)
    parent = operation_parent or Path(tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    operation_root = Path(tempfile.mkdtemp(prefix="m06a-parser-", dir=parent))
    try:
        input_path = operation_root / "verified-input.bin"
        with input_path.open("xb") as handle:
            handle.write(input_bytes)
            handle.flush()
        request = {
            "config_sha256": resources.config_sha256,
            "implementation_sha256": resources.implementation_sha256,
            "output_filename": "candidate-package.json",
            "parser_id": PARSER_ID,
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "security_profile_id": SECURITY_PROFILE_ID,
            "verified_input_relative_name": "verified-input.bin",
            "verified_input_sha256": sha256_bytes(input_bytes),
            "verified_input_size": len(input_bytes),
        }
        request_bytes = canonical_json(request)
        framed = struct.pack(">Q", len(request_bytes)) + request_bytes
        worker_command = (
            [sys.executable, "--m06a-parser-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-I", "-m", "discrepancy_desk.parser_worker"]
        )
        completed = subprocess.run(
            worker_command,
            cwd=operation_root,
            input=framed,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        receipt_path = operation_root / "worker-receipt.json"
        if not receipt_path.is_file():
            raise RuntimeError("parser worker did not preserve a receipt")
        receipt_bytes = receipt_path.read_bytes()
        receipt = load_canonical_json_bytes(receipt_bytes)
        if not isinstance(receipt, dict):
            raise RuntimeError("parser worker receipt is malformed")
        candidate_path = operation_root / "candidate-package.json"
        candidate_bytes: bytes | None = None
        candidate: dict[str, object] | None = None
        if candidate_path.is_file():
            candidate_bytes = candidate_path.read_bytes()
            loaded = load_canonical_json_bytes(candidate_bytes)
            candidate = validate_candidate_core(loaded, input_size=len(input_bytes))
            if receipt.get("candidate_package_sha256") != sha256_bytes(candidate_bytes):
                raise RuntimeError("parser worker receipt does not match candidate bytes")
        if completed.returncode == 0 and candidate is None:
            raise RuntimeError("successful parser worker omitted candidate output")
        if completed.returncode != 0 and candidate is not None:
            raise RuntimeError("failed parser worker emitted candidate output")
        return WorkerResult(
            candidate=candidate,
            candidate_bytes=candidate_bytes,
            receipt=receipt,
            receipt_bytes=receipt_bytes,
            exit_code=completed.returncode,
        )
    finally:
        shutil.rmtree(operation_root, ignore_errors=True)


def assemble_under_test_package(
    input_bytes: bytes,
    *,
    vault_account_id: str,
    source_artifact_sha256: str,
    parser_admission_id: str,
    project_root: Path | None = None,
) -> tuple[dict[str, object], bytes, WorkerResult]:
    resources = load_parser_resources(project_root)
    result = run_under_test_worker(input_bytes, project_root=project_root)
    if result.exit_code != 0 or result.candidate is None:
        raise ValueError(str(result.receipt.get("terminal_outcome", "internal_error")))
    package, rendered = assemble_normalized_package(
        candidate=result.candidate,
        input_size=len(input_bytes),
        vault_account_id=vault_account_id,
        source_artifact_sha256=source_artifact_sha256,
        parser_tuple=resources.parser_tuple(),
        parser_admission_id=parser_admission_id,
    )
    return package, rendered, result
