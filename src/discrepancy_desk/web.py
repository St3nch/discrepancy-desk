from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Body, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .actor_context import ActorContext
from .binding import RevisionBundle
from .editorial_queries import (
    evaluate_ready_to_post,
    get_command_center,
    list_pipeline_view,
    list_schedule,
    recommend_need_a_post,
)
from .db import connect
from .migration_runner import run_guarded_upgrade
from .migration_spec import central_migration_spec, vault_migration_spec
from .operator_service import (
    add_source_record,
    capture_work_item,
    create_owned_account,
    get_control_room_item,
    organize_work_item,
    reject_review,
    reschedule_work_item,
    schedule_work_item,
    set_work_item_tags,
    unschedule_work_item,
)
from .vault_backup import create_vault_generation, verify_and_restore_generation
from .vault_filesystem import ArtifactIntegrityError, ArtifactLimitExceeded
from .vault_ingestion import admit_artifact, list_intake_records, start_intake
from .vault_router import (
    open_registered_vault,
    registry_snapshot,
    selected_vault_health,
    upgrade_registered_vault,
)
from .vault_service import provision_vault
from .persistence import (
    approve_revision,
    create_revision,
    create_successor_revision,
    mark_manual_ready,
    record_metric_snapshot,
    record_publication,
    record_publication_mismatch,
    record_replacement_publication,
    register_evidence,
    transition_work_item,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _operation(prefix: str) -> str:
    return f"web:{prefix}:{uuid4()}"


def _connection(request: Request) -> sqlite3.Connection:
    return connect(request.app.state.database_path)


def _list_items(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        """SELECT id, title, state, created_at, updated_at
        FROM work_items ORDER BY updated_at DESC, id"""
    ).fetchall()
    return [dict(row) for row in rows]


def create_app(
    *,
    database_path: Path | None = None,
    evidence_root: Path | None = None,
    migrations_root: Path | None = None,
    vault_base: Path | None = None,
    vault_migrations_root: Path | None = None,
    vault_owner_actor_id: str = "owner-local",
    desktop_token: str | None = None,
    desktop_api_version: str = "1",
) -> FastAPI:
    resolved_database = database_path or PROJECT_ROOT / "runtime" / "discrepancy-desk.sqlite3"
    resolved_evidence = evidence_root or PROJECT_ROOT / "evidence"
    resolved_migrations = migrations_root or PROJECT_ROOT / "migrations"
    resolved_vault_base = vault_base or resolved_database.parent / "vaults"
    resolved_vault_migrations = (
        vault_migrations_root or resolved_migrations.parent / "vault_migrations"
    )
    resolved_central_spec = central_migration_spec(
        resolved_migrations.parent, resolved_migrations
    )
    resolved_vault_spec = vault_migration_spec(PROJECT_ROOT, resolved_vault_migrations)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database_path = resolved_database
        app.state.evidence_root = resolved_evidence
        app.state.migrations_root = resolved_migrations
        app.state.central_migration_spec = resolved_central_spec
        app.state.vault_base = resolved_vault_base
        app.state.vault_migration_spec = resolved_vault_spec
        app.state.vault_owner_actor_id = vault_owner_actor_id
        app.state.desktop_token = desktop_token
        app.state.desktop_api_version = desktop_api_version
        resolved_evidence.mkdir(parents=True, exist_ok=True)
        run_guarded_upgrade(
            resolved_database,
            resolved_central_spec,
            operation_id=f"startup-{uuid4()}",
            allow_create=True,
        )
        yield

    app = FastAPI(title="The Discrepancy Desk Control Room", lifespan=lifespan)

    @app.middleware("http")
    async def desktop_api_boundary(request: Request, call_next):
        if request.url.path.startswith("/desktop-api/"):
            if desktop_token is None:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "desktop_api_disabled",
                        "message": "Desktop API mode is not enabled.",
                        "preserved": True,
                        "changed": False,
                    },
                )
            supplied = request.headers.get("x-discrepancy-desk-token")
            if supplied != desktop_token:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "desktop_auth_refused",
                        "message": "Desktop launch token is missing or incorrect.",
                        "preserved": True,
                        "changed": False,
                    },
                )
        return await call_next(request)

    def desktop_error(message: str, *, status_code: int = 400) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={
                "error": "desktop_request_refused",
                "message": message,
                "preserved": True,
                "changed": False,
                "safe_next_action": "Refresh governed state and submit a corrected request.",
            },
        )

    def desktop_vault_actor(vault_id: str, operation_key: str) -> ActorContext:
        return ActorContext(
            actor_id=vault_owner_actor_id,
            actor_class="human",
            vault_account_id=vault_id,
            correlation_id=operation_key,
            authentication_source="desktop-launch-token",
            allowed_operation_class="vault_admin",
        )

    @app.get("/desktop-api/v1/health")
    async def desktop_health(request: Request) -> JSONResponse:
        connection = _connection(request)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            migration = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            connection.close()
        return JSONResponse(
            {
                "api_version": desktop_api_version,
                "service": "discrepancy-desk-desktop-backend",
                "status": "healthy" if integrity == "ok" else "unhealthy",
                "sqlite_integrity": integrity,
                "migration": migration,
            }
        )

    @app.get("/desktop-api/v1/vaults")
    async def desktop_vaults(request: Request) -> JSONResponse:
        connection = _connection(request)
        try:
            rows = registry_snapshot(connection)
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "vaults": rows})

    @app.post("/desktop-api/v1/vaults")
    async def desktop_create_vault(
        request: Request, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        display_name = str(payload.get("display_name", "")).strip()
        relative_root = str(payload.get("relative_root", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        account_values = payload.get("owned_account_ids", [])
        if (
            not display_name
            or not relative_root
            or not operation_key
            or not isinstance(account_values, list)
        ):
            return desktop_error(
                "display_name, relative_root, operation_key, and owned_account_ids are required"
            )
        connection = _connection(request)
        try:
            try:
                vault_id = provision_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    migration_spec=request.app.state.vault_migration_spec,
                    display_name=display_name,
                    relative_root=relative_root,
                    owner_actor_id=request.app.state.vault_owner_actor_id,
                    operation_key=operation_key,
                    owned_account_ids=tuple(str(value) for value in account_values),
                )
            except FileExistsError:
                return desktop_error("Vault root is already in use.")
            except FileNotFoundError:
                return desktop_error("Vault resources are unavailable.")
            except PermissionError:
                return desktop_error("Vault operation is not permitted.")
            except RuntimeError:
                return desktop_error("Vault operation requires reconciliation.")
            except ValueError:
                return desktop_error("Vault request violates the governed Vault contract.")
        finally:
            connection.close()
        return JSONResponse(
            status_code=201,
            content={"api_version": desktop_api_version, "vault_id": vault_id},
        )

    @app.get("/desktop-api/v1/vaults/{vault_id}/health")
    async def desktop_vault_health(request: Request, vault_id: str) -> JSONResponse:
        connection = _connection(request)
        try:
            health = selected_vault_health(
                connection,
                vault_base=request.app.state.vault_base,
                vault_id=vault_id,
                migration_spec=request.app.state.vault_migration_spec,
            )
        finally:
            connection.close()
        status_code = 200 if health["status"] == "healthy" else 409
        return JSONResponse(
            status_code=status_code,
            content={"api_version": desktop_api_version, **health},
        )

    @app.post("/desktop-api/v1/vaults/{vault_id}/migrate")
    async def desktop_migrate_vault(
        request: Request,
        vault_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        operation_key = str(payload.get("operation_key", "")).strip()
        if not operation_key:
            return desktop_error("operation_key is required")
        connection = _connection(request)
        try:
            try:
                with upgrade_registered_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    vault_id=vault_id,
                    migration_spec=request.app.state.vault_migration_spec,
                    operation_id=operation_key,
                    actor_id=request.app.state.vault_owner_actor_id,
                ) as opened:
                    migration = opened.connection.execute(
                        "SELECT version_num FROM alembic_version"
                    ).fetchone()[0]
            except (FileNotFoundError, PermissionError, RuntimeError, ValueError, sqlite3.DatabaseError):
                return desktop_error("Vault migration was refused or requires reconciliation.", status_code=409)
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "vault_id": vault_id, "migration": migration})

    @app.post("/desktop-api/v1/vaults/{vault_id}/intake")
    async def desktop_start_vault_intake(
        request: Request,
        vault_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        operation_key = str(payload.get("operation_key", "")).strip()
        client_nonce = str(payload.get("client_nonce", "")).strip()
        expects_bytes = payload.get("expects_bytes")
        advisory_byte_size = payload.get("advisory_byte_size")
        if not operation_key or not client_nonce:
            return desktop_error("operation_key and client_nonce are required")
        if type(expects_bytes) is not bool:
            return desktop_error("expects_bytes must be a boolean")
        if advisory_byte_size is not None and type(advisory_byte_size) is not int:
            return desktop_error("advisory_byte_size must be an integer")
        connection = _connection(request)
        try:
            try:
                with open_registered_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    vault_id=vault_id,
                    migration_spec=request.app.state.vault_migration_spec,
                ) as opened:
                    result = start_intake(
                        opened.connection,
                        actor=desktop_vault_actor(vault_id, operation_key),
                        source_kind=str(payload.get("source_kind", "")).strip(),
                        descriptor_class=str(payload.get("descriptor_class", "none")).strip(),
                        display_label=str(payload.get("display_label", "")).strip(),
                        locator=(str(payload["locator"]).strip() if payload.get("locator") else None),
                        platform_label=(
                            str(payload["platform_label"]).strip()
                            if payload.get("platform_label")
                            else None
                        ),
                        retention_classification=str(
                            payload.get("retention_classification", "missing")
                        ).strip(),
                        policy_basis_reference=str(
                            payload.get("policy_basis_reference", "")
                        ).strip(),
                        human_classification_note=str(
                            payload.get("human_classification_note", "")
                        ).strip(),
                        client_nonce=client_nonce,
                        operation_key=operation_key,
                        expects_bytes=expects_bytes,
                        supplied_filename=(
                            str(payload["supplied_filename"]).strip()
                            if payload.get("supplied_filename")
                            else None
                        ),
                        supplied_media_type=(
                            str(payload["supplied_media_type"]).strip()
                            if payload.get("supplied_media_type")
                            else None
                        ),
                        advisory_byte_size=advisory_byte_size,
                    )
            except FileNotFoundError:
                return desktop_error("Vault resources are unavailable.", status_code=404)
            except PermissionError:
                return desktop_error("Vault intake authority was refused.", status_code=403)
            except (RuntimeError, ValueError, sqlite3.DatabaseError):
                return desktop_error("Vault intake request violates the governed contract.", status_code=409)
        finally:
            connection.close()
        return JSONResponse(
            status_code=201 if result.status != "rejected" else 422,
            content={
                "api_version": desktop_api_version,
                "status": result.status,
                "result_id": result.result_id,
                "acquisition_id": result.acquisition_id,
                "upload_authorization_id": result.upload_authorization_id,
                "reason_code": result.reason_code,
            },
        )

    @app.post("/desktop-api/v1/vaults/{vault_id}/acquisitions/{acquisition_id}/artifact")
    async def desktop_admit_vault_artifact(
        request: Request,
        vault_id: str,
        acquisition_id: str,
        upload_authorization_id: Annotated[str, Form()],
        operation_key: Annotated[str, Form()],
        artifact: Annotated[UploadFile, File()],
    ) -> JSONResponse:
        if not upload_authorization_id.strip() or not operation_key.strip():
            return desktop_error("upload_authorization_id and operation_key are required")
        connection = _connection(request)
        try:
            try:
                with open_registered_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    vault_id=vault_id,
                    migration_spec=request.app.state.vault_migration_spec,
                ) as opened:
                    result = admit_artifact(
                        opened.connection,
                        vault_root=opened.root,
                        actor=desktop_vault_actor(vault_id, operation_key),
                        acquisition_id=acquisition_id,
                        upload_authorization_id=upload_authorization_id,
                        operation_key=operation_key,
                        stream=artifact.file,
                        supplied_filename=artifact.filename,
                        supplied_media_type=artifact.content_type,
                    )
            except ArtifactLimitExceeded:
                return desktop_error("Artifact exceeds the 64 MiB intake ceiling.", status_code=413)
            except ArtifactIntegrityError:
                return desktop_error("Artifact integrity verification failed.", status_code=409)
            except FileNotFoundError:
                return desktop_error("Vault resources are unavailable.", status_code=404)
            except PermissionError:
                return desktop_error("Artifact admission authority was refused.", status_code=403)
            except (RuntimeError, ValueError, sqlite3.DatabaseError):
                return desktop_error("Artifact admission requires reconciliation or corrected input.", status_code=409)
        finally:
            await artifact.close()
            connection.close()
        return JSONResponse(
            status_code=201,
            content={
                "api_version": desktop_api_version,
                "acquisition_id": result.acquisition_id,
                "artifact_id": result.artifact_id,
                "sha256": result.sha256,
                "byte_size": result.byte_size,
                "storage_relative_path": result.storage_relative_path,
                "reused_existing": result.reused_existing,
            },
        )

    @app.get("/desktop-api/v1/vaults/{vault_id}/intake")
    async def desktop_vault_intake_records(request: Request, vault_id: str) -> JSONResponse:
        connection = _connection(request)
        try:
            try:
                with open_registered_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    vault_id=vault_id,
                    migration_spec=request.app.state.vault_migration_spec,
                ) as opened:
                    rows = list_intake_records(
                        opened.connection, vault_account_id=vault_id
                    )
            except (FileNotFoundError, PermissionError, RuntimeError, ValueError, sqlite3.DatabaseError):
                return desktop_error("Vault intake records are unavailable.", status_code=409)
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "vault_id": vault_id, **rows})

    @app.post("/desktop-api/v1/vaults/{vault_id}/backups")
    async def desktop_create_vault_backup(
        request: Request,
        vault_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        operation_key = str(payload.get("operation_key", "")).strip()
        if not operation_key:
            return desktop_error("operation_key is required")
        connection = _connection(request)
        try:
            try:
                with open_registered_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    vault_id=vault_id,
                    migration_spec=request.app.state.vault_migration_spec,
                ) as opened:
                    result = create_vault_generation(
                        opened.connection,
                        vault_root=opened.root,
                        actor=desktop_vault_actor(vault_id, operation_key),
                        migration_head=request.app.state.vault_migration_spec.expected_head,
                    )
            except (FileNotFoundError, PermissionError, RuntimeError, ValueError, sqlite3.DatabaseError):
                return desktop_error("Vault backup could not be completed.", status_code=409)
        finally:
            connection.close()
        return JSONResponse(
            status_code=201,
            content={
                "api_version": desktop_api_version,
                "vault_id": vault_id,
                "generation_id": result.generation_id,
                "manifest_sha256": result.manifest_sha256,
            },
        )

    @app.post("/desktop-api/v1/vaults/{vault_id}/backups/{generation_id}/verify")
    async def desktop_verify_vault_backup(
        request: Request,
        vault_id: str,
        generation_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        operation_key = str(payload.get("operation_key", "")).strip()
        if not operation_key:
            return desktop_error("operation_key is required")
        connection = _connection(request)
        proof_root = request.app.state.database_path.parent / "restore-proofs" / f"proof-{uuid4()}"
        try:
            try:
                with open_registered_vault(
                    connection,
                    vault_base=request.app.state.vault_base,
                    vault_id=vault_id,
                    migration_spec=request.app.state.vault_migration_spec,
                ) as opened:
                    proof = verify_and_restore_generation(
                        opened.connection,
                        vault_root=opened.root,
                        actor=desktop_vault_actor(vault_id, operation_key),
                        generation_id=generation_id,
                        proof_root=proof_root,
                        expected_migration_head=request.app.state.vault_migration_spec.expected_head,
                    )
            except (FileNotFoundError, PermissionError, RuntimeError, ValueError, sqlite3.DatabaseError):
                return desktop_error("Vault backup verification or disposable restore failed.", status_code=409)
        finally:
            connection.close()
            shutil.rmtree(proof_root, ignore_errors=True)
        return JSONResponse(
            {
                "api_version": desktop_api_version,
                "vault_id": vault_id,
                "generation_id": generation_id,
                "status": "verified",
                "manifest_sha256": proof.manifest_sha256,
                "artifact_count": proof.artifact_count,
            }
        )

    @app.get("/desktop-api/v1/accounts")
    async def desktop_accounts(request: Request) -> JSONResponse:
        connection = _connection(request)
        try:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, platform, external_account_id, username FROM owned_accounts ORDER BY id"
                )
            ]
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "accounts": rows})

    @app.get("/desktop-api/v1/command-center")
    async def desktop_command_center(
        request: Request, account_id: Annotated[str, Query()]
    ) -> JSONResponse:
        connection = _connection(request)
        try:
            try:
                center = get_command_center(
                    connection, account_id=account_id, now=datetime.now(timezone.utc).isoformat()
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "account_id": account_id, "data": center})

    @app.get("/desktop-api/v1/ready/{work_item_id}")
    async def desktop_ready(
        request: Request, work_item_id: str, account_id: Annotated[str, Query()]
    ) -> JSONResponse:
        connection = _connection(request)
        try:
            try:
                result = evaluate_ready_to_post(
                    connection, work_item_id=work_item_id, account_id=account_id,
                    now=datetime.now(timezone.utc).isoformat(),
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "data": result})

    @app.post("/desktop-api/v1/work-items")
    async def desktop_capture_work_item(
        request: Request, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        title = str(payload.get("title", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        if not title or not operation_key:
            return desktop_error("title and operation_key are required")
        connection = _connection(request)
        try:
            try:
                work_item_id = capture_work_item(
                    connection,
                    work_item_id=_id("work"),
                    title=title,
                    operation_key=operation_key,
                    actor_id="owner-desktop",
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse(
            status_code=201,
            content={"api_version": desktop_api_version, "work_item_id": work_item_id},
        )

    @app.post("/desktop-api/v1/work-items/{work_item_id}/organize")
    async def desktop_organize_work_item(
        request: Request,
        work_item_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        required = ("account_id", "lane", "operation_key")
        if any(not str(payload.get(name, "")).strip() for name in required):
            return desktop_error("account_id, lane, and operation_key are required")
        connection = _connection(request)
        try:
            try:
                result = organize_work_item(
                    connection,
                    work_item_id=work_item_id,
                    account_id=str(payload["account_id"]),
                    lane=str(payload["lane"]),
                    topic=(str(payload["topic"]).strip() if payload.get("topic") else None),
                    priority=int(payload.get("priority", 3)),
                    operator_notes=(
                        str(payload["operator_notes"]).strip()
                        if payload.get("operator_notes")
                        else None
                    ),
                    is_dormant=bool(payload.get("is_dormant", False)),
                    actor_id="owner-desktop",
                    operation_key=str(payload["operation_key"]),
                )
            except (TypeError, ValueError) as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "work_item_id": result})

    @app.put("/desktop-api/v1/work-items/{work_item_id}/tags")
    async def desktop_set_tags(
        request: Request,
        work_item_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        account_id = str(payload.get("account_id", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        tags = payload.get("tags")
        if not account_id or not operation_key or not isinstance(tags, list):
            return desktop_error("account_id, operation_key, and tags are required")
        connection = _connection(request)
        try:
            try:
                result = set_work_item_tags(
                    connection,
                    work_item_id=work_item_id,
                    account_id=account_id,
                    tags=[str(value) for value in tags],
                    actor_id="owner-desktop",
                    operation_key=operation_key,
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "work_item_id": result})

    @app.get("/desktop-api/v1/schedule")
    async def desktop_schedule_view(
        request: Request,
        account_id: Annotated[str, Query()],
        days: Annotated[int, Query()] = 90,
    ) -> JSONResponse:
        if days < 1 or days > 90:
            return desktop_error("schedule days must be between 1 and 90")
        now = datetime.now(timezone.utc)
        connection = _connection(request)
        try:
            try:
                rows = list_schedule(
                    connection,
                    account_id=account_id,
                    start=now.isoformat(),
                    end=(now + timedelta(days=days)).isoformat(),
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "account_id": account_id, "rows": rows})

    @app.get("/desktop-api/v1/work-items/{work_item_id}")
    async def desktop_work_item(request: Request, work_item_id: str) -> JSONResponse:
        connection = _connection(request)
        try:
            row = connection.execute(
                "SELECT id, title, state, created_at, updated_at FROM work_items WHERE id=?",
                (work_item_id,),
            ).fetchone()
            if row is None:
                return desktop_error("unknown work item", status_code=404)
            profile = connection.execute(
                "SELECT account_id, lane, topic, priority, is_dormant FROM editorial_profiles WHERE work_item_id=?",
                (work_item_id,),
            ).fetchone()
            tags = [value[0] for value in connection.execute(
                "SELECT tag FROM work_item_tags WHERE work_item_id=? ORDER BY tag", (work_item_id,)
            )]
            schedules = [dict(value) for value in connection.execute(
                "SELECT id, account_id, status, scheduled_for, stale_after, supersedes_schedule_id FROM schedule_slots WHERE work_item_id=? ORDER BY created_at DESC, id DESC",
                (work_item_id,),
            )]
        finally:
            connection.close()
        return JSONResponse({
            "api_version": desktop_api_version,
            "work_item": dict(row),
            "profile": dict(profile) if profile is not None else None,
            "tags": tags,
            "schedules": schedules,
        })

    @app.get("/desktop-api/v1/system")
    async def desktop_system(request: Request) -> JSONResponse:
        connection = _connection(request)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            migration = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            counts = {
                "accounts": connection.execute("SELECT count(*) FROM owned_accounts").fetchone()[0],
                "work_items": connection.execute("SELECT count(*) FROM work_items").fetchone()[0],
                "audit_events": connection.execute("SELECT count(*) FROM audit_events").fetchone()[0],
            }
        finally:
            connection.close()
        return JSONResponse({
            "api_version": desktop_api_version,
            "status": "healthy" if integrity == "ok" else "unhealthy",
            "sqlite_integrity": integrity,
            "migration": migration,
            "counts": counts,
        })

    @app.post("/desktop-api/v1/work-items/{work_item_id}/reschedule")
    async def desktop_reschedule_work_item(
        request: Request,
        work_item_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        required = ("account_id", "prior_schedule_id", "scheduled_for", "operation_key")
        if any(not str(payload.get(name, "")).strip() for name in required):
            return desktop_error("account_id, prior_schedule_id, scheduled_for, and operation_key are required")
        connection = _connection(request)
        try:
            try:
                schedule_id = reschedule_work_item(
                    connection,
                    schedule_id=_id("schedule"),
                    prior_schedule_id=str(payload["prior_schedule_id"]),
                    account_id=str(payload["account_id"]),
                    scheduled_for=str(payload["scheduled_for"]),
                    preferred_window_start=None,
                    preferred_window_end=None,
                    earliest_useful_at=None,
                    stale_after=None,
                    hard_deadline_at=None,
                    is_evergreen=False,
                    actor_id="owner-desktop",
                    operation_key=str(payload["operation_key"]),
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "schedule_id": schedule_id, "work_item_id": work_item_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/unschedule")
    async def desktop_unschedule_work_item(
        request: Request,
        work_item_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        required = ("account_id", "prior_schedule_id", "operation_key")
        if any(not str(payload.get(name, "")).strip() for name in required):
            return desktop_error("account_id, prior_schedule_id, and operation_key are required")
        connection = _connection(request)
        try:
            try:
                schedule_id = unschedule_work_item(
                    connection,
                    schedule_id=_id("schedule"),
                    prior_schedule_id=str(payload["prior_schedule_id"]),
                    account_id=str(payload["account_id"]),
                    actor_id="owner-desktop",
                    operation_key=str(payload["operation_key"]),
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "schedule_id": schedule_id, "work_item_id": work_item_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/schedule")
    async def desktop_schedule_work_item(
        request: Request,
        work_item_id: str,
        payload: Annotated[dict[str, object], Body()],
    ) -> JSONResponse:
        account_id = str(payload.get("account_id", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        if not account_id or not operation_key:
            return desktop_error("account_id and operation_key are required")
        connection = _connection(request)
        try:
            try:
                schedule_id = schedule_work_item(
                    connection,
                    schedule_id=_id("schedule"),
                    work_item_id=work_item_id,
                    account_id=account_id,
                    scheduled_for=(
                        str(payload["scheduled_for"]).strip()
                        if payload.get("scheduled_for")
                        else None
                    ),
                    preferred_window_start=None,
                    preferred_window_end=None,
                    earliest_useful_at=None,
                    stale_after=(
                        str(payload["stale_after"]).strip()
                        if payload.get("stale_after")
                        else None
                    ),
                    hard_deadline_at=None,
                    is_evergreen=bool(payload.get("is_evergreen", False)),
                    actor_id="owner-desktop",
                    operation_key=operation_key,
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "schedule_id": schedule_id})

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": str(exc)},
            status_code=400,
        )

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error_handler(request: Request, exc: sqlite3.IntegrityError) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": f"Persistence conflict: {exc}"},
            status_code=409,
        )

    @app.get("/health", response_class=HTMLResponse)
    async def health(request: Request) -> HTMLResponse:
        connection = _connection(request)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            connection.close()
        return TEMPLATES.TemplateResponse(
            request=request,
            name="health.html",
            context={"integrity": integrity, "version": version},
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        account_id: Annotated[str | None, Query()] = None,
    ) -> HTMLResponse:
        connection = _connection(request)
        try:
            items = _list_items(connection)
            accounts = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, platform, external_account_id, username FROM owned_accounts ORDER BY id"
                )
            ]
            selected_account_id = account_id or (str(accounts[0]["id"]) if accounts else None)
            now = datetime.now(timezone.utc).isoformat()
            center = (
                get_command_center(connection, account_id=selected_account_id, now=now)
                if selected_account_id is not None
                else None
            )
            recommendation = (
                recommend_need_a_post(
                    connection,
                    account_id=selected_account_id,
                    slot_start=now,
                    slot_end=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                    now=now,
                )
                if selected_account_id is not None
                else None
            )
        finally:
            connection.close()
        return TEMPLATES.TemplateResponse(
            request=request,
            name="command_center.html",
            context={
                "items": items,
                "accounts": accounts,
                "selected_account_id": selected_account_id,
                "center": center,
                "recommendation": recommendation,
            },
        )

    @app.get("/schedule", response_class=HTMLResponse)
    async def schedule_view(
        request: Request,
        account_id: Annotated[str, Query()],
    ) -> HTMLResponse:
        now_dt = datetime.now(timezone.utc)
        connection = _connection(request)
        try:
            accounts = [dict(row) for row in connection.execute(
                "SELECT id, platform, external_account_id, username FROM owned_accounts ORDER BY id"
            )]
            rows = list_schedule(
                connection, account_id=account_id, start=now_dt.isoformat(),
                end=(now_dt + timedelta(days=90)).isoformat(),
            )
        finally:
            connection.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="schedule.html",
            context={"accounts": accounts, "selected_account_id": account_id, "rows": rows},
        )

    @app.get("/pipeline", response_class=HTMLResponse)
    async def pipeline_view(
        request: Request,
        account_id: Annotated[str, Query()],
        view: Annotated[str, Query()] = "needs_my_review",
    ) -> HTMLResponse:
        connection = _connection(request)
        try:
            accounts = [dict(row) for row in connection.execute(
                "SELECT id, platform, external_account_id, username FROM owned_accounts ORDER BY id"
            )]
            rows = list_pipeline_view(
                connection, account_id=account_id, view_name=view,
                now=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            connection.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="pipeline.html",
            context={
                "accounts": accounts, "selected_account_id": account_id,
                "view_name": view, "rows": rows,
            },
        )

    @app.post("/accounts")
    async def create_account_route(
        request: Request,
        platform: Annotated[str, Form()],
        external_account_id: Annotated[str, Form()],
        username: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            create_owned_account(
                connection,
                account_id=_id("account"),
                platform=platform,
                external_account_id=external_account_id,
                username=username or None,
                operation_key=_operation("account"),
                actor_id="owner-local",
            )
        finally:
            connection.close()
        return RedirectResponse("/", status_code=303)

    @app.post("/work-items")
    async def capture_route(
        request: Request,
        title: Annotated[str, Form()],
    ) -> RedirectResponse:
        work_item_id = _id("work")
        connection = _connection(request)
        try:
            capture_work_item(
                connection,
                work_item_id=work_item_id,
                title=title,
                operation_key=_operation("capture"),
                actor_id="owner-local",
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.get("/work-items/{work_item_id}", response_class=HTMLResponse)
    async def work_item_view(request: Request, work_item_id: str) -> HTMLResponse:
        connection = _connection(request)
        try:
            item = get_control_room_item(connection, work_item_id)
            accounts = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, platform, username FROM owned_accounts ORDER BY id"
                )
            ]
            approvals = [
                dict(row)
                for row in connection.execute(
                    """SELECT a.id, a.revision_id, a.binding_sha256, a.decision, a.decided_at
                    FROM approvals a JOIN revisions r ON r.id=a.revision_id
                    WHERE r.work_item_id=? ORDER BY a.decided_at DESC""",
                    (work_item_id,),
                )
            ]
            profile_row = connection.execute(
                "SELECT * FROM editorial_profiles WHERE work_item_id=?", (work_item_id,)
            ).fetchone()
            profile = dict(profile_row) if profile_row is not None else None
            tags = [row[0] for row in connection.execute(
                "SELECT tag FROM work_item_tags WHERE work_item_id=? ORDER BY tag", (work_item_id,)
            )]
            schedule_history = [dict(row) for row in connection.execute(
                "SELECT * FROM schedule_slots WHERE work_item_id=? ORDER BY created_at DESC, id DESC",
                (work_item_id,),
            )]
            ready = (
                evaluate_ready_to_post(
                    connection, work_item_id=work_item_id,
                    account_id=str(profile["account_id"]),
                    now=datetime.now(timezone.utc).isoformat(),
                )
                if profile is not None else None
            )
        finally:
            connection.close()
        return TEMPLATES.TemplateResponse(
            request=request,
            name="work_item.html",
            context={"item": item, "accounts": accounts, "approvals": approvals, "profile": profile, "tags": tags, "schedule_history": schedule_history, "ready": ready},
        )

    @app.post("/work-items/{work_item_id}/organize")
    async def organize_route(
        request: Request,
        work_item_id: str,
        account_id: Annotated[str, Form()],
        lane: Annotated[str, Form()],
        topic: Annotated[str | None, Form()] = None,
        priority: Annotated[int, Form()] = 3,
        operator_notes: Annotated[str | None, Form()] = None,
        is_dormant: Annotated[bool, Form()] = False,
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            organize_work_item(
                connection, work_item_id=work_item_id, account_id=account_id, lane=lane,
                topic=topic or None, priority=priority, operator_notes=operator_notes or None,
                is_dormant=is_dormant, actor_id="owner-local",
                operation_key=_operation("organize"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/tags")
    async def tags_route(
        request: Request,
        work_item_id: str,
        account_id: Annotated[str, Form()],
        tags_text: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            set_work_item_tags(
                connection, work_item_id=work_item_id, account_id=account_id,
                tags=[value for value in tags_text.split(",")],
                actor_id="owner-local", operation_key=_operation("tags"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/schedule")
    async def schedule_route(
        request: Request,
        work_item_id: str,
        account_id: Annotated[str, Form()],
        scheduled_for: Annotated[str | None, Form()] = None,
        stale_after: Annotated[str | None, Form()] = None,
        is_evergreen: Annotated[bool, Form()] = False,
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            schedule_work_item(
                connection, schedule_id=_id("schedule"), work_item_id=work_item_id,
                account_id=account_id, scheduled_for=scheduled_for or None,
                preferred_window_start=None, preferred_window_end=None,
                earliest_useful_at=None, stale_after=stale_after or None,
                hard_deadline_at=None, is_evergreen=is_evergreen, actor_id="owner-local",
                operation_key=_operation("schedule"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/reschedule")
    async def reschedule_route(
        request: Request,
        work_item_id: str,
        account_id: Annotated[str, Form()],
        prior_schedule_id: Annotated[str, Form()],
        scheduled_for: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            reschedule_work_item(
                connection, schedule_id=_id("schedule"), prior_schedule_id=prior_schedule_id,
                account_id=account_id, scheduled_for=scheduled_for,
                preferred_window_start=None, preferred_window_end=None, earliest_useful_at=None,
                stale_after=None, hard_deadline_at=None, is_evergreen=False,
                actor_id="owner-local", operation_key=_operation("reschedule"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/unschedule")
    async def unschedule_route(
        request: Request,
        work_item_id: str,
        account_id: Annotated[str, Form()],
        prior_schedule_id: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            unschedule_work_item(
                connection, schedule_id=_id("schedule"), prior_schedule_id=prior_schedule_id,
                account_id=account_id, actor_id="owner-local",
                operation_key=_operation("unschedule"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/sources")
    async def add_source_route(
        request: Request,
        work_item_id: str,
        source_kind: Annotated[str, Form()],
        locator: Annotated[str | None, Form()] = None,
        note_text: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            add_source_record(
                connection,
                source_id=_id("source"),
                work_item_id=work_item_id,
                source_kind=source_kind,
                locator=locator or None,
                note_text=note_text or None,
                operation_key=_operation("source"),
                actor_id="owner-local",
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/evidence")
    async def register_evidence_route(
        request: Request,
        work_item_id: str,
        relative_path: Annotated[str, Form()],
    ) -> RedirectResponse:
        candidate = (request.app.state.evidence_root / relative_path).resolve()
        root = request.app.state.evidence_root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("evidence path escapes governed root")
        if not candidate.is_file():
            raise ValueError("evidence file does not exist")
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        connection = _connection(request)
        try:
            register_evidence(
                connection,
                request.app.state.evidence_root,
                evidence_id=_id("evidence"),
                work_item_id=work_item_id,
                relative_path=relative_path,
                expected_sha256=digest,
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/desktop-api/v1/work-items/{work_item_id}/sources")
    async def desktop_add_source(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        source_kind = str(payload.get("source_kind", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        if not source_kind or not operation_key:
            return desktop_error("source_kind and operation_key are required")
        connection = _connection(request)
        try:
            try:
                source_id = _id("source")
                add_source_record(
                    connection,
                    source_id=source_id,
                    work_item_id=work_item_id,
                    source_kind=source_kind,
                    locator=(str(payload["locator"]).strip() if payload.get("locator") else None),
                    note_text=(str(payload["note_text"]).strip() if payload.get("note_text") else None),
                    operation_key=operation_key,
                    actor_id="owner-desktop",
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "source_id": source_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/evidence")
    async def desktop_register_evidence(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        relative_path = str(payload.get("relative_path", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        if not relative_path or not operation_key:
            return desktop_error("relative_path and operation_key are required")
        candidate = (request.app.state.evidence_root / relative_path).resolve()
        root = request.app.state.evidence_root.resolve()
        if root not in candidate.parents and candidate != root:
            return desktop_error("evidence path escapes governed root")
        if not candidate.is_file():
            return desktop_error("evidence file does not exist")
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        connection = _connection(request)
        try:
            try:
                evidence_id = _id("evidence")
                register_evidence(
                    connection,
                    request.app.state.evidence_root,
                    evidence_id=evidence_id,
                    work_item_id=work_item_id,
                    relative_path=relative_path,
                    expected_sha256=digest,
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "evidence_id": evidence_id, "sha256": digest})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/draft")
    async def desktop_draft(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        account_id = str(payload.get("account_id", "")).strip()
        authored_text = str(payload.get("authored_text", ""))
        if not account_id or not authored_text:
            return desktop_error("account_id and authored_text are required")
        connection = _connection(request)
        try:
            try:
                state = connection.execute("SELECT state FROM work_items WHERE id=?", (work_item_id,)).fetchone()
                if state is None:
                    raise ValueError("unknown work item")
                if state[0] in {"captured", "research_ready", "rejected", "withdrawn"}:
                    transition_work_item(connection, work_item_id, "drafting", actor_id="owner-desktop")
                elif state[0] != "drafting":
                    raise ValueError("draft creation requires captured, research_ready, rejected, withdrawn, or drafting state")
                account = connection.execute("SELECT platform FROM owned_accounts WHERE id=?", (account_id,)).fetchone()
                if account is None:
                    raise ValueError("unknown owned account")
                revision_id = _id("revision")
                create_revision(
                    connection,
                    revision_id=revision_id,
                    work_item_id=work_item_id,
                    owned_account_id=account_id,
                    bundle=RevisionBundle(str(account[0]), account_id, authored_text),
                )
                transition_work_item(connection, work_item_id, "human_review_needed", actor_id="owner-desktop")
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "revision_id": revision_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/approve")
    async def desktop_approve(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        revision_id = str(payload.get("revision_id", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        if not revision_id or not operation_key:
            return desktop_error("revision_id and operation_key are required")
        connection = _connection(request)
        try:
            try:
                row = connection.execute("SELECT binding_sha256, work_item_id FROM revisions WHERE id=?", (revision_id,)).fetchone()
                if row is None or row[1] != work_item_id:
                    raise ValueError("revision does not belong to work item")
                approval_id = _id("approval")
                approve_revision(
                    connection,
                    approval_id=approval_id,
                    revision_id=revision_id,
                    binding_sha256=str(row[0]),
                    actor_id="owner-desktop",
                    action_id=operation_key,
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "approval_id": approval_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/manual-ready")
    async def desktop_manual_ready(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        approval_id = str(payload.get("approval_id", "")).strip()
        operation_key = str(payload.get("operation_key", "")).strip()
        if not approval_id or not operation_key:
            return desktop_error("approval_id and operation_key are required")
        connection = _connection(request)
        try:
            try:
                mark_manual_ready(connection, work_item_id=work_item_id, approval_id=approval_id, actor_id="owner-desktop", operation_key=operation_key)
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "work_item_id": work_item_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/publication")
    async def desktop_publication(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        required = ("revision_id", "approval_id", "external_post_id", "canonical_url", "operation_key")
        if any(not str(payload.get(name, "")).strip() for name in required):
            return desktop_error("revision_id, approval_id, external_post_id, canonical_url, and operation_key are required")
        connection = _connection(request)
        try:
            try:
                revision = connection.execute("SELECT platform, owned_account_id, work_item_id FROM revisions WHERE id=?", (str(payload["revision_id"]),)).fetchone()
                if revision is None or revision[2] != work_item_id:
                    raise ValueError("revision does not belong to work item")
                publication_id = _id("publication")
                common = dict(
                    connection=connection,
                    publication_id=publication_id,
                    revision_id=str(payload["revision_id"]),
                    approval_id=str(payload["approval_id"]),
                    platform=str(revision[0]),
                    owned_account_id=str(revision[1]),
                    external_post_id=str(payload["external_post_id"]),
                    canonical_url=str(payload["canonical_url"]),
                    actor_id="owner-desktop",
                    operation_key=str(payload["operation_key"]),
                )
                mismatch_reason = str(payload.get("mismatch_reason", "")).strip()
                replaces = str(payload.get("replaces_publication_id", "")).strip()
                if replaces:
                    record_replacement_publication(**common, replaces_publication_id=replaces)
                elif mismatch_reason:
                    record_publication_mismatch(**common, mismatch_reason=mismatch_reason)
                else:
                    record_publication(**common)
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "publication_id": publication_id})

    @app.post("/desktop-api/v1/work-items/{work_item_id}/metrics")
    async def desktop_metrics(
        request: Request, work_item_id: str, payload: Annotated[dict[str, object], Body()]
    ) -> JSONResponse:
        operation_key = str(payload.get("operation_key", "")).strip()
        observation_state = str(payload.get("observation_state", "")).strip()
        metrics = payload.get("metrics")
        if not operation_key or not observation_state or metrics is None:
            return desktop_error("operation_key, observation_state, and metrics are required")
        connection = _connection(request)
        try:
            try:
                publication = connection.execute("SELECT p.id FROM publications p JOIN revisions r ON r.id=p.revision_id WHERE r.work_item_id=? ORDER BY p.observed_at DESC LIMIT 1", (work_item_id,)).fetchone()
                if publication is None:
                    raise ValueError("metrics require a publication")
                snapshot_id = _id("metric")
                record_metric_snapshot(
                    connection,
                    snapshot_id=snapshot_id,
                    publication_id=str(publication[0]),
                    observation_method="manual",
                    capture_session_id=operation_key,
                    metric_set_version=1,
                    metrics=metrics,
                    observation_state=observation_state,
                    actor_id="owner-desktop",
                    operation_key=operation_key,
                )
            except ValueError as exc:
                return desktop_error(str(exc))
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "snapshot_id": snapshot_id})

    @app.get("/desktop-api/v1/records")
    async def desktop_records(request: Request, account_id: Annotated[str, Query()]) -> JSONResponse:
        connection = _connection(request)
        try:
            rows = []
            for row in connection.execute(
                "SELECT s.id, s.work_item_id, s.source_kind, s.locator, s.note_text FROM source_records s JOIN editorial_profiles ep ON ep.work_item_id=s.work_item_id WHERE ep.account_id=? ORDER BY s.created_at DESC, s.id",
                (account_id,),
            ):
                item = dict(row)
                if isinstance(item["note_text"], bytes):
                    item["note_text"] = item["note_text"].decode("utf-8")
                rows.append(item)
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "account_id": account_id, "rows": rows})

    @app.get("/desktop-api/v1/metrics")
    async def desktop_metrics_view(request: Request, account_id: Annotated[str, Query()]) -> JSONResponse:
        connection = _connection(request)
        try:
            rows = []
            for row in connection.execute(
                "SELECT ms.id, ms.publication_id, ms.captured_at, ms.observation_state, ms.metrics_json FROM metric_snapshots ms JOIN publications p ON p.id=ms.publication_id WHERE p.owned_account_id=? ORDER BY ms.captured_at DESC, ms.id",
                (account_id,),
            ):
                item = dict(row)
                raw_metrics = item["metrics_json"]
                if isinstance(raw_metrics, bytes):
                    item["metrics"] = json.loads(raw_metrics.decode("utf-8"))
                else:
                    item["metrics"] = json.loads(str(raw_metrics))
                del item["metrics_json"]
                rows.append(item)
        finally:
            connection.close()
        return JSONResponse({"api_version": desktop_api_version, "account_id": account_id, "rows": rows})

    @app.post("/work-items/{work_item_id}/draft")
    async def draft_route(
        request: Request,
        work_item_id: str,
        owned_account_id: Annotated[str, Form()],
        authored_text: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            state = connection.execute(
                "SELECT state FROM work_items WHERE id=?", (work_item_id,)
            ).fetchone()
            if state is None:
                raise ValueError("unknown work item")
            if state[0] in {"captured", "research_ready", "rejected", "withdrawn"}:
                transition_work_item(connection, work_item_id, "drafting", actor_id="owner-local")
            elif state[0] != "drafting":
                raise ValueError("draft creation requires captured, research_ready, rejected, withdrawn, or drafting state")
            account = connection.execute(
                "SELECT platform FROM owned_accounts WHERE id=?", (owned_account_id,)
            ).fetchone()
            if account is None:
                raise ValueError("unknown owned account")
            create_revision(
                connection,
                revision_id=_id("revision"),
                work_item_id=work_item_id,
                owned_account_id=owned_account_id,
                bundle=RevisionBundle(str(account[0]), owned_account_id, authored_text),
            )
            transition_work_item(
                connection, work_item_id, "human_review_needed", actor_id="owner-local"
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)


    @app.post("/work-items/{work_item_id}/revise")
    async def revise_route(
        request: Request,
        work_item_id: str,
        predecessor_revision_id: Annotated[str, Form()],
        authored_text: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            predecessor = connection.execute(
                "SELECT platform, owned_account_id, work_item_id FROM revisions WHERE id=?",
                (predecessor_revision_id,),
            ).fetchone()
            if predecessor is None or predecessor[2] != work_item_id:
                raise ValueError("predecessor revision does not belong to work item")
            create_successor_revision(
                connection,
                revision_id=_id("revision"),
                predecessor_revision_id=predecessor_revision_id,
                work_item_id=work_item_id,
                owned_account_id=str(predecessor[1]),
                bundle=RevisionBundle(str(predecessor[0]), str(predecessor[1]), authored_text),
                actor_id="owner-local",
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/approve")
    async def approve_route(
        request: Request,
        work_item_id: str,
        revision_id: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            row = connection.execute(
                "SELECT binding_sha256, work_item_id FROM revisions WHERE id=?", (revision_id,)
            ).fetchone()
            if row is None or row[1] != work_item_id:
                raise ValueError("revision does not belong to work item")
            approve_revision(
                connection,
                approval_id=_id("approval"),
                revision_id=revision_id,
                binding_sha256=str(row[0]),
                actor_id="owner-local",
                action_id=_operation("approve"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/reject")
    async def reject_route(
        request: Request,
        work_item_id: str,
        reason: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            reject_review(
                connection,
                work_item_id=work_item_id,
                reason=reason,
                actor_id="owner-local",
                operation_key=_operation("reject"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/manual-ready")
    async def manual_ready_route(
        request: Request,
        work_item_id: str,
        approval_id: Annotated[str, Form()],
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            mark_manual_ready(
                connection,
                work_item_id=work_item_id,
                approval_id=approval_id,
                actor_id="owner-local",
                operation_key=_operation("manual-ready"),
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/publication")
    async def publication_route(
        request: Request,
        work_item_id: str,
        revision_id: Annotated[str, Form()],
        approval_id: Annotated[str, Form()],
        external_post_id: Annotated[str, Form()],
        canonical_url: Annotated[str, Form()],
        mismatch_reason: Annotated[str | None, Form()] = None,
        replaces_publication_id: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        connection = _connection(request)
        try:
            revision = connection.execute(
                "SELECT platform, owned_account_id, work_item_id FROM revisions WHERE id=?",
                (revision_id,),
            ).fetchone()
            if revision is None or revision[2] != work_item_id:
                raise ValueError("revision does not belong to work item")
            common = dict(
                connection=connection,
                publication_id=_id("publication"),
                revision_id=revision_id,
                approval_id=approval_id,
                platform=str(revision[0]),
                owned_account_id=str(revision[1]),
                external_post_id=external_post_id,
                canonical_url=canonical_url,
                actor_id="owner-local",
                operation_key=_operation("publication"),
            )
            if replaces_publication_id and replaces_publication_id.strip():
                record_replacement_publication(
                    **common, replaces_publication_id=replaces_publication_id
                )
            elif mismatch_reason and mismatch_reason.strip():
                record_publication_mismatch(**common, mismatch_reason=mismatch_reason)
            else:
                record_publication(**common)
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    @app.post("/work-items/{work_item_id}/metrics")
    async def metric_route(
        request: Request,
        work_item_id: str,
        observation_method: Annotated[str, Form()],
        observation_state: Annotated[str, Form()],
        metrics_json: Annotated[str, Form()],
    ) -> RedirectResponse:
        try:
            metrics = json.loads(metrics_json)
        except json.JSONDecodeError as exc:
            raise ValueError("metrics must be valid JSON") from exc
        connection = _connection(request)
        try:
            publication = connection.execute(
                """SELECT p.id FROM publications p JOIN revisions r ON r.id=p.revision_id
                WHERE r.work_item_id=? ORDER BY p.observed_at DESC LIMIT 1""",
                (work_item_id,),
            ).fetchone()
            if publication is None:
                raise ValueError("metrics require a publication")
            record_metric_snapshot(
                connection,
                snapshot_id=_id("metric"),
                publication_id=str(publication[0]),
                observation_method=observation_method,
                capture_session_id=_operation("metric-session"),
                metric_set_version=1,
                metrics=metrics,
                observation_state=observation_state,
            )
        finally:
            connection.close()
        return RedirectResponse(f"/work-items/{work_item_id}", status_code=303)

    return app


def desktop_runtime_config_from_env() -> dict[str, object]:
    token = os.environ.get("DISCREPANCY_DESK_DESKTOP_TOKEN", "")
    host = os.environ.get("DISCREPANCY_DESK_DESKTOP_HOST", "")
    port_text = os.environ.get("DISCREPANCY_DESK_DESKTOP_PORT", "")
    if host != "127.0.0.1":
        raise ValueError("desktop backend host must be 127.0.0.1")
    if len(token) < 32:
        raise ValueError("desktop launch token is missing or too short")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("desktop backend port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("desktop backend port is outside the valid range")
    database = os.environ.get("DISCREPANCY_DESK_DESKTOP_DATABASE", "")
    evidence = os.environ.get("DISCREPANCY_DESK_DESKTOP_EVIDENCE_ROOT", "")
    migrations = os.environ.get("DISCREPANCY_DESK_DESKTOP_MIGRATIONS_ROOT", "")
    if not database or not evidence or not migrations:
        raise ValueError("desktop database, evidence root, and migrations root are required")
    return {
        "host": host,
        "port": port,
        "token": token,
        "database_path": Path(database),
        "evidence_root": Path(evidence),
        "migrations_root": Path(migrations),
    }


def desktop_main() -> None:
    import uvicorn

    config = desktop_runtime_config_from_env()
    app = create_app(
        database_path=config["database_path"],
        evidence_root=config["evidence_root"],
        migrations_root=config["migrations_root"],
        desktop_token=str(config["token"]),
        desktop_api_version="1",
    )
    uvicorn.run(
        app,
        host=str(config["host"]),
        port=int(config["port"]),
        access_log=False,
        log_level="warning",
    )


app = create_app()
