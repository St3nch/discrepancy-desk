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
from .vtt_contract import (
    INITIAL_VTT_CONFIG,
    VTT_CONFIG_SHA256,
    VTT_DEPENDENCY_LOCK_SHA256,
    VTT_IMPLEMENTATION_SHA256,
    VTT_IMPLEMENTATION_VERSION,
    VTT_PACKAGE_SCHEMA_VERSION,
    VTT_PARSER_ID,
    VTT_RESOURCE_MANIFEST_SHA256,
    VTT_SCHEMA_SHA256,
    VTT_SECURITY_PROFILE_ID,
    VTT_WARNING_POLICY_VERSION,
    VTT_WORKER_PROTOCOL_VERSION,
    assemble_vtt_normalized_package,
    canonical_vtt_config_bytes,
    sha256_file,
    vtt_parser_tuple,
    validate_vtt_candidate,
)
from .vault_persistence import append_vault_audit, request_hash, utc_now


@dataclass(frozen=True, slots=True)
class VttResources:
    root: Path
    manifest_sha256: str
    config_sha256: str
    schema_sha256: str
    implementation_sha256: str
    dependency_lock_sha256: str

    def parser_tuple(self) -> ParserTuple:
        return vtt_parser_tuple(
            resource_manifest_sha256=self.manifest_sha256,
            dependency_lock_sha256=self.dependency_lock_sha256,
            config_sha256=self.config_sha256,
        )


@dataclass(frozen=True, slots=True)
class VttWorkerResult:
    candidate: dict[str, object] | None
    candidate_bytes: bytes | None
    receipt: dict[str, object]
    receipt_bytes: bytes
    exit_code: int


def _resource_candidates(project_root: Path | None = None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if project_root is not None:
        candidates.append(project_root / "parser_resources" / VTT_PARSER_ID)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "parser_resources" / VTT_PARSER_ID)
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "parser_resources" / VTT_PARSER_ID,
            Path(sys.executable).resolve().parent / "parser_resources" / VTT_PARSER_ID,
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def locate_vtt_resources(project_root: Path | None = None) -> Path:
    for candidate in _resource_candidates(project_root):
        if (candidate / "manifest.sha256").is_file():
            return candidate
    raise FileNotFoundError("VTT parser resources are unavailable")


def _parse_manifest(path: Path) -> dict[tuple[str, str], str]:
    entries: dict[tuple[str, str], str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 3:
            raise ValueError("VTT parser manifest line is malformed")
        kind, resource_path, digest = parts
        key = (kind, resource_path)
        if key in entries:
            raise ValueError("VTT parser manifest contains a duplicate entry")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("VTT parser manifest hash is invalid")
        entries[key] = digest
    return entries


def load_vtt_resources_from_root(
    root: Path, *, dependency_lock_path: Path | None = None
) -> VttResources:
    resolved_root = root.resolve(strict=True)
    manifest_path = resolved_root / "manifest.sha256"
    if not manifest_path.is_file() or sha256_file(manifest_path) != VTT_RESOURCE_MANIFEST_SHA256:
        raise ValueError("VTT parser resource manifest does not match D045")
    entries = _parse_manifest(manifest_path)
    required = {
        ("config", "config.json"),
        ("dependency-lock", "uv.lock"),
        ("implementation", "discrepancy_desk.parsers.vtt_v1"),
        ("schema", "schema.json"),
    }
    if set(entries) != required:
        raise ValueError("VTT parser manifest entries diverge from the D045 set")
    expected_entries = {
        ("config", "config.json"): VTT_CONFIG_SHA256,
        ("dependency-lock", "uv.lock"): VTT_DEPENDENCY_LOCK_SHA256,
        ("implementation", "discrepancy_desk.parsers.vtt_v1"): VTT_IMPLEMENTATION_SHA256,
        ("schema", "schema.json"): VTT_SCHEMA_SHA256,
    }
    if entries != expected_entries:
        raise ValueError("VTT parser manifest hashes diverge from D045")

    config_path = resolved_root / "config.json"
    schema_path = resolved_root / "schema.json"
    config_sha = sha256_file(config_path)
    schema_sha = sha256_file(schema_path)
    if config_sha != VTT_CONFIG_SHA256:
        raise ValueError("VTT parser configuration hash mismatch")
    if schema_sha != VTT_SCHEMA_SHA256:
        raise ValueError("VTT parser schema hash mismatch")
    config_bytes = config_path.read_bytes()
    if (
        config_bytes != canonical_vtt_config_bytes()
        or json.loads(config_bytes.decode("utf-8")) != INITIAL_VTT_CONFIG
    ):
        raise ValueError("VTT parser configuration bytes are not canonical")

    package_root = Path(__file__).resolve().parent
    implementation_path = package_root / "parsers" / "vtt_v1.py"
    if (
        not implementation_path.is_file()
        or sha256_file(implementation_path) != VTT_IMPLEMENTATION_SHA256
    ):
        raise ValueError("VTT parser implementation bytes diverge from D045")

    lock_candidates = (
        [dependency_lock_path]
        if dependency_lock_path is not None
        else [
            resolved_root.parents[1] / "uv.lock",
            Path(sys.executable).resolve().parent / "uv.lock",
        ]
    )
    lock_path = next(
        (path for path in lock_candidates if path is not None and path.is_file()), None
    )
    if lock_path is None:
        raise FileNotFoundError("VTT dependency lock bytes are unavailable")
    if sha256_file(lock_path) != VTT_DEPENDENCY_LOCK_SHA256:
        raise ValueError("VTT dependency lock bytes diverge from D045")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("$id") != "urn:discrepancy-desk:m06a.normalized-package.vtt.v1":
        raise ValueError("VTT parser schema identity mismatch")
    return VttResources(
        root=resolved_root,
        manifest_sha256=VTT_RESOURCE_MANIFEST_SHA256,
        config_sha256=VTT_CONFIG_SHA256,
        schema_sha256=VTT_SCHEMA_SHA256,
        implementation_sha256=VTT_IMPLEMENTATION_SHA256,
        dependency_lock_sha256=VTT_DEPENDENCY_LOCK_SHA256,
    )


def load_vtt_resources(project_root: Path | None = None) -> VttResources:
    return load_vtt_resources_from_root(locate_vtt_resources(project_root))


def _candidate_ids(resources: VttResources) -> tuple[str, str, str]:
    parser_tuple = resources.parser_tuple()
    definition_material = {
        key: value for key, value in parser_tuple.material().items() if key != "config_sha256"
    }
    definition_hash = sha256_bytes(canonical_json(definition_material))
    tuple_hash = parser_tuple.sha256()
    definition_id = f"parser-definition-m06a-vtt-v1-{definition_hash[:16]}"
    config_id = f"parser-config-m06a-vtt-v1-{definition_hash[:12]}-{resources.config_sha256[:16]}"
    admission_id = f"parser-admission-m06a-vtt-v1-under-test-{tuple_hash[:16]}"
    return definition_id, config_id, admission_id


def _pending_evidence_hash(label: str) -> str:
    return sha256_bytes(f"m06a.vtt.v1:under-test:{label}:pending".encode("utf-8"))


def install_under_test_vtt_candidate(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    project_root: Path | None = None,
) -> tuple[str, str, str]:
    resources = load_vtt_resources(project_root)
    parser_tuple = resources.parser_tuple()
    definition_id, config_id, admission_id = _candidate_ids(resources)
    metadata = connection.execute(
        "SELECT vault_account_id FROM vault_metadata WHERE singleton_id=1"
    ).fetchone()
    if metadata is None:
        raise ValueError("Vault metadata is unavailable for VTT candidate installation")
    vault_account_id = str(metadata[0])
    actor_row = connection.execute(
        "SELECT actor_class, status, authority_profile FROM actors WHERE vault_account_id=? AND id=?",
        (vault_account_id, actor_id),
    ).fetchone()
    if actor_row is None or str(actor_row[0]) != "human" or str(actor_row[1]) != "active":
        raise PermissionError("VTT candidate installation requires the active Vault owner")
    authorities = {value.strip() for value in str(actor_row[2]).split(",") if value.strip()}
    if "vault_admin" not in authorities and "*" not in authorities:
        raise PermissionError("VTT candidate installation requires Vault administration authority")

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
            raise ValueError("installed VTT candidate tuple conflicts with packaged resources")
        return definition_id, config_id, admission_id
    if connection.execute(
        "SELECT 1 FROM parser_definitions WHERE vault_account_id=? AND id=?",
        (vault_account_id, definition_id),
    ).fetchone() is not None:
        raise ValueError("VTT parser definition exists with an unrecognized tuple")

    created_at = utc_now()
    actor = ActorContext(
        actor_id=actor_id,
        actor_class="human",
        vault_account_id=vault_account_id,
        correlation_id=f"install:{admission_id}",
        authentication_source="governed-vtt-parser-installation",
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
            VALUES (?, ?, 'text/vtt', 'internal',
                    'discrepancy_desk.parsers.vtt_v1:parse_bytes', ?, ?, ?, ?,
                    'project-code', ?, ?, ?, ?, ?)""",
            (
                definition_id,
                vault_account_id,
                VTT_IMPLEMENTATION_VERSION,
                parser_tuple.implementation_sha256,
                parser_tuple.resource_manifest_sha256,
                parser_tuple.dependency_lock_sha256,
                VTT_PACKAGE_SCHEMA_VERSION,
                parser_tuple.deterministic_contract_version,
                VTT_SECURITY_PROFILE_ID,
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
                canonical_vtt_config_bytes(),
                parser_tuple.config_sha256,
                int(INITIAL_VTT_CONFIG["input_size_limit_bytes"]),
                int(INITIAL_VTT_CONFIG["cue_limit"]),
                int(INITIAL_VTT_CONFIG["line_limit"]),
                int(INITIAL_VTT_CONFIG["maximum_cue_bytes"]),
                VTT_WARNING_POLICY_VERSION,
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
                "D045 VTT candidate; owner admission and canonical execution are blocked",
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


def _unavailable_vtt_status() -> dict[str, object]:
    return {
        "parser_definition_id": "parser-definition-m06a-vtt-v1-unavailable",
        "parser_id": VTT_PARSER_ID,
        "display_name": "WebVTT",
        "state": "unavailable",
        "canonical_available": False,
        "admission_ready": False,
        "admission_manifest": None,
        "reason_code": "packaged_tuple_mismatch",
        "package_schema_version": VTT_PACKAGE_SCHEMA_VERSION,
        "security_profile_id": VTT_SECURITY_PROFILE_ID,
    }


def list_vtt_status(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    project_root: Path | None = None,
) -> dict[str, object]:
    try:
        resources = load_vtt_resources(project_root)
    except (OSError, ValueError, json.JSONDecodeError):
        return _unavailable_vtt_status()
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
        "parser_id": VTT_PARSER_ID,
        "display_name": "WebVTT",
        "state": state,
        "canonical_available": False,
        "admission_ready": False,
        "admission_manifest": None,
        "reason_code": (
            "owner_admission_not_authorized" if row is not None else "candidate_not_installed"
        ),
        "package_schema_version": VTT_PACKAGE_SCHEMA_VERSION,
        "security_profile_id": VTT_SECURITY_PROFILE_ID,
    }


def run_under_test_vtt_worker(
    input_bytes: bytes,
    *,
    operation_parent: Path | None = None,
    project_root: Path | None = None,
    timeout_seconds: int = 30,
) -> VttWorkerResult:
    resources = load_vtt_resources(project_root)
    parent = operation_parent or Path(tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    operation_root = Path(tempfile.mkdtemp(prefix="m06a-vtt-parser-", dir=parent))
    try:
        input_path = operation_root / "verified-input.bin"
        with input_path.open("xb") as handle:
            handle.write(input_bytes)
            handle.flush()
        request = {
            "config_sha256": resources.config_sha256,
            "implementation_sha256": resources.implementation_sha256,
            "output_filename": "candidate-package.json",
            "parser_id": VTT_PARSER_ID,
            "protocol_version": VTT_WORKER_PROTOCOL_VERSION,
            "security_profile_id": VTT_SECURITY_PROFILE_ID,
            "verified_input_relative_name": "verified-input.bin",
            "verified_input_sha256": sha256_bytes(input_bytes),
            "verified_input_size": len(input_bytes),
        }
        request_bytes = canonical_json(request)
        framed = struct.pack(">Q", len(request_bytes)) + request_bytes
        worker_command = (
            [sys.executable, "--m06a-vtt-parser-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-I", "-m", "discrepancy_desk.vtt_worker"]
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
            raise RuntimeError("VTT parser worker did not preserve a receipt")
        receipt_bytes = receipt_path.read_bytes()
        receipt = load_canonical_json_bytes(receipt_bytes)
        if not isinstance(receipt, dict):
            raise RuntimeError("VTT parser worker receipt is malformed")
        candidate_path = operation_root / "candidate-package.json"
        candidate_bytes: bytes | None = None
        candidate: dict[str, object] | None = None
        if candidate_path.is_file():
            candidate_bytes = candidate_path.read_bytes()
            loaded = load_canonical_json_bytes(candidate_bytes)
            candidate = validate_vtt_candidate(loaded, input_bytes=input_bytes)
            if receipt.get("candidate_package_sha256") != sha256_bytes(candidate_bytes):
                raise RuntimeError("VTT worker receipt does not match candidate bytes")
        if completed.returncode == 0 and candidate is None:
            raise RuntimeError("successful VTT worker omitted candidate output")
        if completed.returncode != 0 and candidate is not None:
            raise RuntimeError("failed VTT worker emitted candidate output")
        return VttWorkerResult(
            candidate=candidate,
            candidate_bytes=candidate_bytes,
            receipt=receipt,
            receipt_bytes=receipt_bytes,
            exit_code=completed.returncode,
        )
    finally:
        shutil.rmtree(operation_root, ignore_errors=True)


def assemble_under_test_vtt_package(
    input_bytes: bytes,
    *,
    vault_account_id: str,
    source_artifact_sha256: str,
    parser_admission_id: str,
    project_root: Path | None = None,
) -> tuple[dict[str, object], bytes, VttWorkerResult]:
    resources = load_vtt_resources(project_root)
    result = run_under_test_vtt_worker(input_bytes, project_root=project_root)
    if result.exit_code != 0 or result.candidate is None:
        raise ValueError(str(result.receipt.get("terminal_outcome", "internal_error")))
    package, rendered = assemble_vtt_normalized_package(
        candidate=result.candidate,
        input_bytes=input_bytes,
        vault_account_id=vault_account_id,
        source_artifact_sha256=source_artifact_sha256,
        parser_tuple=resources.parser_tuple(),
        parser_admission_id=parser_admission_id,
    )
    return package, rendered, result
