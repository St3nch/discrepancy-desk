from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .parser_contract import PACKAGE_SCHEMA_VERSION, PARSER_ID, SECURITY_PROFILE_ID
from .parser_service import list_parser_status
from .srt_contract import SRT_PACKAGE_SCHEMA_VERSION, SRT_PARSER_ID, SRT_SECURITY_PROFILE_ID
from .srt_service import list_srt_status
from .vtt_contract import VTT_PACKAGE_SCHEMA_VERSION, VTT_PARSER_ID, VTT_SECURITY_PROFILE_ID
from .vtt_service import list_vtt_status

_STATUS_ERRORS = (OSError, ValueError, json.JSONDecodeError, sqlite3.DatabaseError)


def _unavailable(
    *, parser_id: str, display_name: str, package_schema_version: str, security_profile_id: str
) -> dict[str, object]:
    safe_id = parser_id.replace('.', '-')
    return {
        "parser_definition_id": f"parser-definition-{safe_id}-unavailable",
        "parser_id": parser_id,
        "display_name": display_name,
        "state": "unavailable",
        "canonical_available": False,
        "admission_ready": False,
        "admission_manifest": None,
        "reason_code": "packaged_tuple_mismatch",
        "package_schema_version": package_schema_version,
        "security_profile_id": security_profile_id,
    }


def list_all_parser_status(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    project_root: Path | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        text_rows = list_parser_status(
            connection, vault_account_id=vault_account_id, project_root=project_root
        )
    except _STATUS_ERRORS:
        text_rows = [
            _unavailable(
                parser_id=PARSER_ID,
                display_name="Plain Text",
                package_schema_version=PACKAGE_SCHEMA_VERSION,
                security_profile_id=SECURITY_PROFILE_ID,
            )
        ]
    rows.extend(text_rows)

    try:
        rows.append(
            list_srt_status(
                connection, vault_account_id=vault_account_id, project_root=project_root
            )
        )
    except _STATUS_ERRORS:
        rows.append(
            _unavailable(
                parser_id=SRT_PARSER_ID,
                display_name="SubRip (SRT)",
                package_schema_version=SRT_PACKAGE_SCHEMA_VERSION,
                security_profile_id=SRT_SECURITY_PROFILE_ID,
            )
        )

    try:
        rows.append(
            list_vtt_status(
                connection, vault_account_id=vault_account_id, project_root=project_root
            )
        )
    except _STATUS_ERRORS:
        rows.append(
            _unavailable(
                parser_id=VTT_PARSER_ID,
                display_name="WebVTT",
                package_schema_version=VTT_PACKAGE_SCHEMA_VERSION,
                security_profile_id=VTT_SECURITY_PROFILE_ID,
            )
        )
    return rows
