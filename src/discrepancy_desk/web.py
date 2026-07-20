from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
) -> FastAPI:
    resolved_database = database_path or PROJECT_ROOT / "runtime" / "discrepancy-desk.sqlite3"
    resolved_evidence = evidence_root or PROJECT_ROOT / "evidence"
    resolved_migrations = migrations_root or PROJECT_ROOT / "migrations"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database_path = resolved_database
        app.state.evidence_root = resolved_evidence
        app.state.migrations_root = resolved_migrations
        resolved_evidence.mkdir(parents=True, exist_ok=True)
        run_guarded_upgrade(
            resolved_database,
            resolved_migrations,
            operation_id=f"startup-{uuid4()}",
        )
        yield

    app = FastAPI(title="The Discrepancy Desk Control Room", lifespan=lifespan)

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


app = create_app()
