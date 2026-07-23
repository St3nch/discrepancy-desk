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
from typing import Mapping
from uuid import uuid4

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
    require_deterministic_candidates,
    require_sha256,
    sha256_bytes,
    sha256_file,
    validate_candidate_core,
)
from .parser_worker import sanitized_worker_environment
from .vault_filesystem import store_package_bytes, verify_artifact_file
from .vault_persistence import (
    append_vault_audit,
    existing_vault_operation,
    record_vault_operation,
    request_hash,
    utc_now,
)

TEXT_ADMISSION_CONFIRMATION = "ADMIT m06a.text.v1 FOR THIS VAULT"
TEXT_FIXTURE_MANIFEST_SHA256 = "5d9b3776becf33ca19464790b0b9136aa8744954e870d21b14893586c0a8d0c7"
TEXT_FOCUSED_EVIDENCE_SHA256 = "dab23159b696574ee972aa5ecec3037fcef546a72f6f6a7ca8fedf81df54185e"
TEXT_NO_EGRESS_EVIDENCE_SHA256 = "28a462caf68f4bd98703f225b51188e69a2055dff0bb1143558f67a48fd48889"
TEXT_PACKAGED_EVIDENCE_SHA256 = "b98df13a904efecb2740061628fba13716e7effba88a104aceb5c0b89e12f31d"
TEXT_ADMISSION_MATERIAL_SHA256 = "82de317451a7bbe3ac5f303bddec5459001193155b196d7796d162abb34b5dba"


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


@dataclass(frozen=True, slots=True)
class TextAdmissionResult:
    parser_admission_version_id: str
    parser_definition_id: str
    parser_configuration_version_id: str
    state: str
    canonical_available: bool
    replayed: bool


@dataclass(frozen=True, slots=True)
class CanonicalTextResult:
    parser_execution_id: str
    normalized_package_id: str | None
    document_version_id: str | None
    package_sha256: str | None
    state: str
    terminal_outcome: str
    reused_package: bool
    reused_document: bool
    replayed: bool


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
    if not source_path.is_file():
        raise FileNotFoundError("parser implementation source bytes are unavailable")
    if sha256_file(source_path) != implementation_sha:
        raise ValueError("parser implementation bytes diverge from the admitted hash")
    dependency_sha = entries[("dependency-lock", "uv.lock")]
    lock_candidates = [root.parent / "uv.lock", Path(sys.executable).resolve().parent / "uv.lock"]
    existing_lock = next((path for path in lock_candidates if path.is_file()), None)
    if existing_lock is None:
        raise FileNotFoundError("parser dependency lock bytes are unavailable")
    if sha256_file(existing_lock) != dependency_sha:
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
    parser_tuple = resources.parser_tuple()
    definition_material = {
        key: value
        for key, value in parser_tuple.material().items()
        if key != "config_sha256"
    }
    definition_hash = sha256_bytes(canonical_json(definition_material))
    tuple_hash = parser_tuple.sha256()
    definition_id = f"parser-definition-m06a-text-v1-{definition_hash[:16]}"
    config_id = (
        f"parser-config-m06a-text-v1-{definition_hash[:12]}-"
        f"{resources.config_sha256[:16]}"
    )
    admission_id = f"parser-admission-m06a-text-v1-under-test-{tuple_hash[:16]}"
    return definition_id, config_id, admission_id



def _require_active_vault_owner(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
) -> None:
    row = connection.execute(
        """SELECT actor_class, status, authority_profile
        FROM actors WHERE vault_account_id=? AND id=?""",
        (actor.vault_account_id, actor.actor_id),
    ).fetchone()
    if row is None or str(row[0]) != "human" or str(row[1]) != "active":
        raise PermissionError("plain-text authority requires the active human Vault owner")
    authorities = {value.strip() for value in str(row[2]).split(",") if value.strip()}
    if "vault_admin" not in authorities and "*" not in authorities:
        raise PermissionError("plain-text authority requires Vault administration authority")


def text_admission_manifest(project_root: Path | None = None) -> dict[str, str]:
    resources = load_parser_resources(project_root)
    definition_id, config_id, under_test_id = _candidate_ids(resources)
    material = {
        "parser_definition_id": definition_id,
        "parser_configuration_version_id": config_id,
        "state": "owner_admitted",
        "fixture_manifest_sha256": TEXT_FIXTURE_MANIFEST_SHA256,
        "focused_test_evidence_sha256": TEXT_FOCUSED_EVIDENCE_SHA256,
        "no_egress_evidence_sha256": TEXT_NO_EGRESS_EVIDENCE_SHA256,
        "packaged_sidecar_evidence_sha256": TEXT_PACKAGED_EVIDENCE_SHA256,
        "dependency_lock_sha256": resources.dependency_lock_sha256,
        "supersedes_admission_id": under_test_id,
    }
    material_sha256 = sha256_bytes(canonical_json(material))
    if material_sha256 != TEXT_ADMISSION_MATERIAL_SHA256:
        raise ValueError("plain-text admission material diverges from D039")
    return {
        **material,
        "admission_material_sha256": material_sha256,
        "parser_admission_version_id": (
            f"parser-admission-m06a-text-v1-owner-admitted-{material_sha256[:16]}"
        ),
        "confirmation_text": TEXT_ADMISSION_CONFIRMATION,
    }


def _admission_result(
    connection: sqlite3.Connection,
    admission_id: str,
    *,
    replayed: bool,
) -> TextAdmissionResult:
    row = connection.execute(
        """SELECT parser_definition_id, parser_configuration_version_id, state
        FROM parser_admission_versions WHERE id=?""",
        (admission_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("plain-text admission result is unavailable")
    return TextAdmissionResult(
        parser_admission_version_id=admission_id,
        parser_definition_id=str(row[0]),
        parser_configuration_version_id=str(row[1]),
        state=str(row[2]),
        canonical_available=str(row[2]) == "owner_admitted",
        replayed=replayed,
    )


def admit_text_parser(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    operation_key: str,
    confirmation_text: str,
    expected_manifest: Mapping[str, object],
    project_root: Path | None = None,
) -> TextAdmissionResult:
    if confirmation_text != TEXT_ADMISSION_CONFIRMATION:
        raise PermissionError("exact plain-text admission confirmation is required")
    if not operation_key or len(operation_key) > 200:
        raise ValueError("plain-text admission operation key is invalid")
    _require_active_vault_owner(connection, actor=actor)
    manifest = text_admission_manifest(project_root)
    if dict(expected_manifest) != manifest:
        raise ValueError("plain-text admission request does not match D039 material")
    request_sha256 = request_hash(
        {
            "confirmation_text": confirmation_text,
            "manifest": manifest,
            "operation_key": operation_key,
        }
    )
    replay = existing_vault_operation(
        connection,
        actor=actor,
        operation_type="m06a_text_owner_admission",
        operation_key=operation_key,
        request_sha256=request_sha256,
    )
    if replay is not None:
        return _admission_result(connection, replay, replayed=True)

    resources = load_parser_resources(project_root)
    parser_tuple = resources.parser_tuple()
    definition_id = manifest["parser_definition_id"]
    config_id = manifest["parser_configuration_version_id"]
    under_test_id = manifest["supersedes_admission_id"]
    owner_admission_id = manifest["parser_admission_version_id"]
    definition = connection.execute(
        """SELECT implementation_version, implementation_sha256,
                  resource_manifest_sha256, dependency_lock_sha256,
                  package_schema_version, deterministic_contract_version,
                  security_profile_id
        FROM parser_definitions
        WHERE vault_account_id=? AND id=?""",
        (actor.vault_account_id, definition_id),
    ).fetchone()
    expected_definition = (
        parser_tuple.implementation_version,
        parser_tuple.implementation_sha256,
        parser_tuple.resource_manifest_sha256,
        parser_tuple.dependency_lock_sha256,
        parser_tuple.package_schema_version,
        parser_tuple.deterministic_contract_version,
        parser_tuple.security_profile_id,
    )
    if definition is None or tuple(str(value) for value in definition) != expected_definition:
        raise ValueError("plain-text parser definition does not match the D039 tuple")
    config = connection.execute(
        """SELECT config_sha256 FROM parser_configuration_versions
        WHERE vault_account_id=? AND id=? AND parser_definition_id=?""",
        (actor.vault_account_id, config_id, definition_id),
    ).fetchone()
    if config is None or str(config[0]) != parser_tuple.config_sha256:
        raise ValueError("plain-text parser configuration does not match D039")

    connection.execute("BEGIN IMMEDIATE")
    try:
        current = connection.execute(
            """SELECT a.id, a.state
            FROM parser_admission_versions a
            WHERE a.vault_account_id=?
              AND a.parser_definition_id=?
              AND a.parser_configuration_version_id=?
              AND NOT EXISTS (
                  SELECT 1 FROM parser_admission_versions successor
                  WHERE successor.vault_account_id=a.vault_account_id
                    AND successor.supersedes_admission_id=a.id
              )
            ORDER BY a.created_at, a.id""",
            (actor.vault_account_id, definition_id, config_id),
        ).fetchall()
        if len(current) != 1 or str(current[0][0]) != under_test_id or str(current[0][1]) != "under_test":
            raise PermissionError("plain-text admission requires the exact current under-test row")
        if connection.execute(
            "SELECT 1 FROM parser_admission_versions WHERE id=?",
            (owner_admission_id,),
        ).fetchone() is not None:
            raise ValueError("plain-text owner-admission ID already exists outside this operation")
        admitted_at = utc_now()
        connection.execute(
            """INSERT INTO parser_admission_versions
            (id, vault_account_id, parser_definition_id, parser_configuration_version_id,
             state, fixture_manifest_sha256, focused_test_evidence_sha256,
             no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
             dependency_lock_sha256, admitted_by_actor_id, admitted_at,
             supersedes_admission_id, reason, created_at, created_by_actor_id)
            VALUES (?, ?, ?, ?, 'owner_admitted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_admission_id,
                actor.vault_account_id,
                definition_id,
                config_id,
                TEXT_FIXTURE_MANIFEST_SHA256,
                TEXT_FOCUSED_EVIDENCE_SHA256,
                TEXT_NO_EGRESS_EVIDENCE_SHA256,
                TEXT_PACKAGED_EVIDENCE_SHA256,
                resources.dependency_lock_sha256,
                actor.actor_id,
                admitted_at,
                under_test_id,
                "D039 exact owner-approved plain-text admission package",
                admitted_at,
                actor.actor_id,
            ),
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="parser_admission_version",
            record_id=owner_admission_id,
            payload={
                "parser_id": PARSER_ID,
                "state": "owner_admitted",
                "supersedes_admission_id": under_test_id,
                "admission_material_sha256": TEXT_ADMISSION_MATERIAL_SHA256,
            },
        )
        record_vault_operation(
            connection,
            actor=actor,
            operation_type="m06a_text_owner_admission",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=owner_admission_id,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _admission_result(connection, owner_admission_id, replayed=False)

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
                "D037 corrected under-test candidate; owner admission is separately blocked",
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
    definition_id, _, _ = _candidate_ids(resources)
    try:
        manifest = text_admission_manifest(project_root)
    except ValueError:
        return [
            {
                "parser_definition_id": definition_id,
                "parser_id": PARSER_ID,
                "display_name": "Plain Text",
                "state": "unavailable",
                "canonical_available": False,
                "admission_ready": False,
                "reason_code": "packaged_tuple_mismatch",
                "package_schema_version": PACKAGE_SCHEMA_VERSION,
                "security_profile_id": SECURITY_PROFILE_ID,
            }
        ]
    rows = connection.execute(
        """SELECT d.id, d.format_id, d.package_schema_version, d.security_profile_id,
                  d.implementation_sha256, d.resource_manifest_sha256, d.dependency_lock_sha256,
                  c.id, c.config_sha256, a.id, a.state,
                  a.fixture_manifest_sha256, a.focused_test_evidence_sha256,
                  a.no_egress_evidence_sha256, a.packaged_sidecar_evidence_sha256,
                  a.dependency_lock_sha256, a.supersedes_admission_id
        FROM parser_definitions d
        JOIN parser_configuration_versions c
          ON c.vault_account_id=d.vault_account_id AND c.parser_definition_id=d.id
        JOIN parser_admission_versions a
          ON a.vault_account_id=d.vault_account_id
         AND a.parser_definition_id=d.id
         AND a.parser_configuration_version_id=c.id
        WHERE d.vault_account_id=? AND d.id=?
          AND NOT EXISTS (
              SELECT 1 FROM parser_admission_versions successor
              WHERE successor.vault_account_id=a.vault_account_id
                AND successor.supersedes_admission_id=a.id
          )
        ORDER BY d.id, a.created_at, a.id""",
        (vault_account_id, definition_id),
    ).fetchall()
    if not rows:
        return []
    if len(rows) != 1:
        return [
            {
                "parser_definition_id": definition_id,
                "parser_id": PARSER_ID,
                "display_name": "Plain Text",
                "state": "unavailable",
                "canonical_available": False,
                "admission_ready": False,
                "reason_code": "ambiguous_current_admission",
                "package_schema_version": PACKAGE_SCHEMA_VERSION,
                "security_profile_id": SECURITY_PROFILE_ID,
            }
        ]
    row = rows[0]
    tuple_matches = (
        str(row[4]) == resources.implementation_sha256
        and str(row[5]) == resources.manifest_sha256
        and str(row[6]) == resources.dependency_lock_sha256
        and str(row[8]) == resources.config_sha256
        and str(row[2]) == PACKAGE_SCHEMA_VERSION
        and str(row[3]) == SECURITY_PROFILE_ID
    )
    state = str(row[10])
    under_test_ready = (
        tuple_matches
        and state == "under_test"
        and str(row[9]) == manifest["supersedes_admission_id"]
    )
    owner_evidence_matches = (
        state == "owner_admitted"
        and str(row[9]) == manifest["parser_admission_version_id"]
        and str(row[11]) == TEXT_FIXTURE_MANIFEST_SHA256
        and str(row[12]) == TEXT_FOCUSED_EVIDENCE_SHA256
        and str(row[13]) == TEXT_NO_EGRESS_EVIDENCE_SHA256
        and str(row[14]) == TEXT_PACKAGED_EVIDENCE_SHA256
        and str(row[15]) == resources.dependency_lock_sha256
        and str(row[16]) == manifest["supersedes_admission_id"]
    )
    canonical_available = bool(tuple_matches and owner_evidence_matches)
    return [
        {
            "parser_definition_id": definition_id,
            "parser_configuration_version_id": str(row[7]),
            "parser_admission_version_id": str(row[9]),
            "parser_id": PARSER_ID,
            "display_name": "Plain Text",
            "format_id": str(row[1]),
            "state": state if tuple_matches else "unavailable",
            "canonical_available": canonical_available,
            "admission_ready": under_test_ready,
            "admission_manifest": manifest if under_test_ready else None,
            "reason_code": (
                None
                if canonical_available
                else "ready_for_owner_admission"
                if under_test_ready
                else "admission_evidence_mismatch"
                if tuple_matches and state == "owner_admitted"
                else "not_owner_admitted"
                if tuple_matches
                else "packaged_tuple_mismatch"
            ),
            "package_schema_version": str(row[2]),
            "security_profile_id": str(row[3]),
        }
    ]


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
            env=sanitized_worker_environment(),
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
            candidate = validate_candidate_core(loaded, input_bytes=input_bytes)
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
        input_bytes=input_bytes,
        vault_account_id=vault_account_id,
        source_artifact_sha256=source_artifact_sha256,
        parser_tuple=resources.parser_tuple(),
        parser_admission_id=parser_admission_id,
    )
    return package, rendered, result


def _canonical_text_result(
    connection: sqlite3.Connection,
    execution_id: str,
    *,
    replayed: bool,
) -> CanonicalTextResult:
    execution = connection.execute(
        """SELECT acquisition_artifact_link_id, state, terminal_outcome, package_sha256
        FROM parser_executions WHERE id=?""",
        (execution_id,),
    ).fetchone()
    if execution is None:
        raise RuntimeError("canonical parser execution result is unavailable")
    package_row = connection.execute(
        """SELECT normalized_package_id FROM parser_execution_package_links
        WHERE parser_execution_id=?""",
        (execution_id,),
    ).fetchone()
    package_id = str(package_row[0]) if package_row is not None else None
    document_id: str | None = None
    if package_id is not None:
        document = connection.execute(
            """SELECT dv.id
            FROM document_versions dv
            JOIN parser_executions origin
              ON origin.vault_account_id=dv.vault_account_id
             AND origin.id=dv.parser_execution_id
            WHERE dv.vault_account_id=(SELECT vault_account_id FROM parser_executions WHERE id=?)
              AND dv.normalized_package_id=?
              AND origin.acquisition_artifact_link_id=?
            ORDER BY dv.version_ordinal, dv.id""",
            (execution_id, package_id, str(execution[0])),
        ).fetchall()
        if len(document) > 1:
            raise RuntimeError("canonical document lineage is ambiguous")
        if document:
            document_id = str(document[0][0])
    package_origin = None
    if package_id is not None:
        package_origin = connection.execute(
            "SELECT parser_execution_id FROM normalized_packages WHERE id=?",
            (package_id,),
        ).fetchone()
    return CanonicalTextResult(
        parser_execution_id=execution_id,
        normalized_package_id=package_id,
        document_version_id=document_id,
        package_sha256=str(execution[3]) if execution[3] is not None else None,
        state=str(execution[1]),
        terminal_outcome=str(execution[2]),
        reused_package=bool(package_origin is not None and str(package_origin[0]) != execution_id),
        reused_document=bool(document_id is not None and package_origin is not None and str(package_origin[0]) != execution_id),
        replayed=replayed,
    )


def _safe_terminal_outcome(value: object) -> str:
    allowed = {
        "encoding_failure",
        "limit_exceeded",
        "malformed_input",
        "partial_output_failure",
        "security_boundary_violation",
        "determinism_failure",
        "packaging_mismatch",
        "internal_error",
    }
    rendered = str(value or "internal_error")
    return rendered if rendered in allowed else "internal_error"


def _finalize_failed_text_execution(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    execution_id: str,
    operation_key: str,
    request_sha256: str,
    terminal_outcome: str,
    receipt_bytes: bytes,
) -> CanonicalTextResult:
    terminal = _safe_terminal_outcome(terminal_outcome)
    connection.execute("BEGIN IMMEDIATE")
    try:
        updated = connection.execute(
            """UPDATE parser_executions
            SET state='failed', terminal_outcome=?, warning_codes_json=?,
                finished_at=?, worker_receipt_sha256=?, error_code=?
            WHERE id=? AND state='started'""",
            (
                terminal,
                canonical_json([]),
                utc_now(),
                sha256_bytes(receipt_bytes),
                f"parser_{terminal}",
                execution_id,
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("parser execution failure could not be finalized")
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="parser_execution",
            record_id=execution_id,
            payload={"state": "failed", "terminal_outcome": terminal},
        )
        record_vault_operation(
            connection,
            actor=actor,
            operation_type="m06a_text_canonical_execution",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=execution_id,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _canonical_text_result(connection, execution_id, replayed=False)


def canonical_parse_text(
    connection: sqlite3.Connection,
    *,
    vault_root: Path,
    actor: ActorContext,
    acquisition_artifact_link_id: str,
    operation_key: str,
    expected_parser_admission_version_id: str,
    project_root: Path | None = None,
    fail_after_package_store: bool = False,
) -> CanonicalTextResult:
    if not operation_key or len(operation_key) > 200:
        raise ValueError("canonical parse operation key is invalid")
    if not acquisition_artifact_link_id:
        raise ValueError("acquisition artifact link ID is required")
    _require_active_vault_owner(connection, actor=actor)
    selection = resolve_canonical_parser(
        connection,
        vault_account_id=actor.vault_account_id,
        acquisition_artifact_link_id=acquisition_artifact_link_id,
        project_root=project_root,
    )
    if expected_parser_admission_version_id != selection.parser_admission_version_id:
        raise ValueError("canonical parse request names a stale parser admission")
    artifact_path = verify_artifact_file(
        vault_root,
        artifact_sha256=selection.artifact_sha256,
        expected_size=selection.artifact_size,
        storage_relative_path=selection.artifact_relative_path,
    )
    input_bytes = artifact_path.read_bytes()
    request_sha256 = request_hash(
        {
            "acquisition_artifact_link_id": acquisition_artifact_link_id,
            "operation_key": operation_key,
            "parser_admission_version_id": selection.parser_admission_version_id,
            "parser_definition_id": selection.parser_definition_id,
            "parser_configuration_version_id": selection.parser_configuration_version_id,
            "input_sha256": selection.artifact_sha256,
            "input_size_bytes": selection.artifact_size,
        }
    )
    replay = existing_vault_operation(
        connection,
        actor=actor,
        operation_type="m06a_text_canonical_execution",
        operation_key=operation_key,
        request_sha256=request_sha256,
    )
    if replay is not None:
        return _canonical_text_result(connection, replay, replayed=True)
    if connection.execute(
        "SELECT 1 FROM parser_executions WHERE vault_account_id=? AND operation_id=?",
        (actor.vault_account_id, operation_key),
    ).fetchone() is not None:
        raise RuntimeError("canonical parse operation requires reconciliation")
    identity = connection.execute(
        "SELECT vault_instance_id FROM vault_metadata WHERE singleton_id=1 AND vault_account_id=?",
        (actor.vault_account_id,),
    ).fetchone()
    if identity is None:
        raise ValueError("Vault identity is unavailable for canonical parsing")
    execution_id = f"parser-execution-{uuid4()}"
    started_at = utc_now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """INSERT INTO parser_executions
            (id, vault_account_id, vault_instance_id, acquisition_artifact_link_id,
             parser_definition_id, parser_configuration_version_id,
             parser_admission_version_id, security_profile_id, input_sha256,
             input_size_bytes, state, terminal_outcome, warning_codes_json,
             started_at, finished_at, worker_receipt_sha256, package_sha256,
             error_code, operation_id, actor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'started', NULL, ?, ?, NULL, NULL, NULL, NULL, ?, ?)""",
            (
                execution_id,
                actor.vault_account_id,
                str(identity[0]),
                acquisition_artifact_link_id,
                selection.parser_definition_id,
                selection.parser_configuration_version_id,
                selection.parser_admission_version_id,
                selection.parser_tuple.security_profile_id,
                selection.artifact_sha256,
                selection.artifact_size,
                canonical_json([]),
                started_at,
                operation_key,
                actor.actor_id,
            ),
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="parser_execution",
            record_id=execution_id,
            payload={
                "state": "started",
                "parser_id": PARSER_ID,
                "acquisition_artifact_link_id": acquisition_artifact_link_id,
            },
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    try:
        first = run_under_test_worker(input_bytes, project_root=project_root)
    except Exception as exc:
        parent_receipt = canonical_json(
            {
                "error_code": type(exc).__name__,
                "preserved": True,
                "schema_version": 1,
                "terminal_outcome": "internal_error",
            }
        )
        return _finalize_failed_text_execution(
            connection,
            actor=actor,
            execution_id=execution_id,
            operation_key=operation_key,
            request_sha256=request_sha256,
            terminal_outcome="internal_error",
            receipt_bytes=parent_receipt,
        )
    if first.exit_code != 0 or first.candidate is None or first.candidate_bytes is None:
        return _finalize_failed_text_execution(
            connection,
            actor=actor,
            execution_id=execution_id,
            operation_key=operation_key,
            request_sha256=request_sha256,
            terminal_outcome=str(first.receipt.get("terminal_outcome", "internal_error")),
            receipt_bytes=first.receipt_bytes,
        )
    try:
        second = run_under_test_worker(input_bytes, project_root=project_root)
    except Exception as exc:
        parent_receipt = canonical_json(
            {
                "error_code": type(exc).__name__,
                "preserved": True,
                "schema_version": 1,
                "terminal_outcome": "internal_error",
            }
        )
        return _finalize_failed_text_execution(
            connection,
            actor=actor,
            execution_id=execution_id,
            operation_key=operation_key,
            request_sha256=request_sha256,
            terminal_outcome="internal_error",
            receipt_bytes=parent_receipt,
        )
    if second.exit_code != 0 or second.candidate_bytes is None:
        return _finalize_failed_text_execution(
            connection,
            actor=actor,
            execution_id=execution_id,
            operation_key=operation_key,
            request_sha256=request_sha256,
            terminal_outcome="determinism_failure",
            receipt_bytes=second.receipt_bytes,
        )
    try:
        require_deterministic_candidates(first.candidate_bytes, second.candidate_bytes)
        package, package_bytes = assemble_normalized_package(
            candidate=first.candidate,
            input_bytes=input_bytes,
            vault_account_id=actor.vault_account_id,
            source_artifact_sha256=selection.artifact_sha256,
            parser_tuple=selection.parser_tuple,
            parser_admission_id=selection.parser_admission_version_id,
        )
    except Exception as exc:
        terminal = (
            "determinism_failure"
            if exc.__class__.__name__ == "DeterminismFailure"
            else "partial_output_failure"
            if exc.__class__.__name__ == "PartialOutputFailure"
            else "packaging_mismatch"
        )
        receipt = canonical_json(
            {"schema_version": 1, "terminal_outcome": terminal, "preserved": True}
        )
        return _finalize_failed_text_execution(
            connection,
            actor=actor,
            execution_id=execution_id,
            operation_key=operation_key,
            request_sha256=request_sha256,
            terminal_outcome=terminal,
            receipt_bytes=receipt,
        )

    stored = store_package_bytes(vault_root, package_bytes)
    if fail_after_package_store:
        raise RuntimeError("synthetic package-before-database failure")
    warnings = list(package["warnings"])
    state = "succeeded_with_warnings" if warnings else "succeeded"
    outcome = "success_with_warnings" if warnings else "success"
    coverage_sha256 = sha256_bytes(canonical_json(package["coverage"]))
    package_id: str
    document_id: str
    reused_package = False
    reused_document = False
    connection.execute("BEGIN IMMEDIATE")
    try:
        updated = connection.execute(
            """UPDATE parser_executions
            SET state=?, terminal_outcome=?, warning_codes_json=?, finished_at=?,
                worker_receipt_sha256=?, package_sha256=?, error_code=NULL
            WHERE id=? AND state='started'""",
            (
                state,
                outcome,
                canonical_json(warnings),
                utc_now(),
                sha256_bytes(first.receipt_bytes),
                stored.sha256,
                execution_id,
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("canonical parser execution could not be finalized")
        existing_package = connection.execute(
            """SELECT id, package_schema_version, package_sha256, byte_size,
                      storage_relative_path, coverage_sha256, warning_codes_json, state
            FROM normalized_packages
            WHERE vault_account_id=? AND storage_relative_path=?""",
            (actor.vault_account_id, stored.storage_relative_path),
        ).fetchone()
        if existing_package is None:
            package_id = f"normalized-package-{stored.sha256}"
            connection.execute(
                """INSERT INTO normalized_packages
                (id, vault_account_id, parser_execution_id, package_schema_version,
                 package_sha256, byte_size, storage_relative_path, coverage_sha256,
                 warning_codes_json, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'current', ?)""",
                (
                    package_id,
                    actor.vault_account_id,
                    execution_id,
                    PACKAGE_SCHEMA_VERSION,
                    stored.sha256,
                    stored.byte_size,
                    stored.storage_relative_path,
                    coverage_sha256,
                    canonical_json(warnings),
                    utc_now(),
                ),
            )
        else:
            expected = (
                PACKAGE_SCHEMA_VERSION,
                stored.sha256,
                stored.byte_size,
                stored.storage_relative_path,
                coverage_sha256,
                canonical_json(warnings),
                "current",
            )
            observed = (
                str(existing_package[1]),
                str(existing_package[2]),
                int(existing_package[3]),
                str(existing_package[4]),
                str(existing_package[5]),
                bytes(existing_package[6]),
                str(existing_package[7]),
            )
            if observed != expected:
                raise ValueError("existing canonical package record conflicts with package bytes")
            package_id = str(existing_package[0])
            connection.execute(
                """INSERT INTO parser_execution_package_links
                (vault_account_id, parser_execution_id, normalized_package_id, created_at)
                VALUES (?, ?, ?, ?)""",
                (actor.vault_account_id, execution_id, package_id, utc_now()),
            )
            reused_package = True

        prior_documents = connection.execute(
            """SELECT dv.id, dv.normalized_package_id, dv.source_artifact_sha256,
                      dv.version_ordinal, dv.state
            FROM document_versions dv
            JOIN parser_executions prior
              ON prior.vault_account_id=dv.vault_account_id
             AND prior.id=dv.parser_execution_id
            WHERE dv.vault_account_id=?
              AND prior.acquisition_artifact_link_id=?
            ORDER BY dv.version_ordinal, dv.id""",
            (actor.vault_account_id, acquisition_artifact_link_id),
        ).fetchall()
        if len(prior_documents) > 1:
            raise RuntimeError("plain-text initial document lineage is ambiguous")
        if prior_documents:
            prior = prior_documents[0]
            if (
                str(prior[1]) != package_id
                or str(prior[2]) != selection.artifact_sha256
                or int(prior[3]) != 1
                or str(prior[4]) != "current"
            ):
                raise PermissionError("canonical parse would require document-version transition authority")
            document_id = str(prior[0])
            reused_document = True
        else:
            document_material = canonical_json(
                {
                    "vault_account_id": actor.vault_account_id,
                    "acquisition_artifact_link_id": acquisition_artifact_link_id,
                    "normalized_package_id": package_id,
                    "version_ordinal": 1,
                }
            )
            document_id = f"document-version-{sha256_bytes(document_material)}"
            connection.execute(
                """INSERT INTO document_versions
                (id, vault_account_id, normalized_package_id, source_artifact_sha256,
                 parser_execution_id, version_ordinal, state, created_at)
                VALUES (?, ?, ?, ?, ?, 1, 'current', ?)""",
                (
                    document_id,
                    actor.vault_account_id,
                    package_id,
                    selection.artifact_sha256,
                    execution_id,
                    utc_now(),
                ),
            )
            for element in package["elements"]:
                ordinal = int(element["ordinal"])
                element_id = f"element-{sha256_bytes(f'{document_id}:{ordinal}'.encode('utf-8'))}"
                connection.execute(
                    """INSERT INTO elements
                    (id, vault_account_id, document_version_id, ordinal, element_kind,
                     source_locator_json, raw_text, normalized_text, content_sha256,
                     warning_codes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        element_id,
                        actor.vault_account_id,
                        document_id,
                        ordinal,
                        str(element["kind"]),
                        canonical_json(element["source_locator"]),
                        str(element["raw_text"]),
                        str(element["normalized_text"]),
                        str(element["content_sha256"]),
                        canonical_json(element["warnings"]),
                    ),
                )
            for region in package["regions"]:
                ordinal = int(region["ordinal"])
                region_id = f"region-{sha256_bytes(f'{document_id}:{ordinal}'.encode('utf-8'))}"
                connection.execute(
                    """INSERT INTO regions
                    (id, vault_account_id, document_version_id, element_id, ordinal,
                     region_kind, source_locator_json, content_sha256)
                    VALUES (?, ?, ?, NULL, ?, ?, ?, ?)""",
                    (
                        region_id,
                        actor.vault_account_id,
                        document_id,
                        ordinal,
                        str(region["kind"]),
                        canonical_json(region["source_locator"]),
                        str(region["content_sha256"]),
                    ),
                )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="document_version",
            record_id=document_id,
            payload={
                "parser_execution_id": execution_id,
                "normalized_package_id": package_id,
                "package_sha256": stored.sha256,
                "reused_package": reused_package,
                "reused_document": reused_document,
                "version_ordinal": 1,
            },
        )
        record_vault_operation(
            connection,
            actor=actor,
            operation_type="m06a_text_canonical_execution",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=execution_id,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    result = _canonical_text_result(connection, execution_id, replayed=False)
    return CanonicalTextResult(
        parser_execution_id=result.parser_execution_id,
        normalized_package_id=result.normalized_package_id,
        document_version_id=result.document_version_id,
        package_sha256=result.package_sha256,
        state=result.state,
        terminal_outcome=result.terminal_outcome,
        reused_package=reused_package,
        reused_document=reused_document,
        replayed=False,
    )


def list_canonical_documents(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in connection.execute(
            """SELECT dv.id AS document_version_id,
                      pe.acquisition_artifact_link_id,
                      dv.normalized_package_id,
                      np.package_sha256,
                      dv.source_artifact_sha256,
                      dv.version_ordinal,
                      dv.state,
                      pe.id AS parser_execution_id,
                      pe.parser_admission_version_id,
                      pe.terminal_outcome,
                      dv.created_at,
                      (SELECT count(*) FROM elements e
                       WHERE e.vault_account_id=dv.vault_account_id
                         AND e.document_version_id=dv.id) AS element_count,
                      (SELECT count(*) FROM regions r
                       WHERE r.vault_account_id=dv.vault_account_id
                         AND r.document_version_id=dv.id) AS region_count
            FROM document_versions dv
            JOIN normalized_packages np
              ON np.vault_account_id=dv.vault_account_id
             AND np.id=dv.normalized_package_id
            JOIN parser_executions pe
              ON pe.vault_account_id=dv.vault_account_id
             AND pe.id=dv.parser_execution_id
            WHERE dv.vault_account_id=?
            ORDER BY dv.created_at DESC, dv.id DESC""",
            (vault_account_id,),
        )
    ]
