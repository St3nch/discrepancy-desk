"""Initial bounded persistence contract.

Revision ID: 0001
Revises: None
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE owned_accounts (
        id TEXT PRIMARY KEY,
        platform TEXT NOT NULL CHECK (platform IN ('x','truth_social')),
        external_account_id TEXT NOT NULL,
        username TEXT,
        owned INTEGER NOT NULL CHECK (owned IN (0,1)),
        UNIQUE(platform, external_account_id)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE work_items (
        id TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK (state IN (
            'captured','research_needed','research_ready','drafting','human_review_needed',
            'approved','manual_ready','published','rejected','withdrawn',
            'publication_mismatch','evidence_blocked')),
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE evidence_refs (
        id TEXT PRIMARY KEY,
        work_item_id TEXT NOT NULL REFERENCES work_items(id) ON DELETE RESTRICT,
        relative_path TEXT NOT NULL CHECK (relative_path NOT LIKE '/%' AND relative_path NOT LIKE '%..%'),
        sha256 TEXT NOT NULL CHECK (length(sha256)=64),
        byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
        verification_state TEXT NOT NULL CHECK (verification_state IN ('unverified','verified','mismatch','missing','orphaned')),
        captured_at TEXT NOT NULL,
        UNIQUE(relative_path),
        UNIQUE(work_item_id, sha256)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE revisions (
        id TEXT PRIMARY KEY,
        work_item_id TEXT NOT NULL REFERENCES work_items(id) ON DELETE RESTRICT,
        platform TEXT NOT NULL CHECK (platform IN ('x','truth_social')),
        owned_account_id TEXT NOT NULL REFERENCES owned_accounts(id) ON DELETE RESTRICT,
        authored_text BLOB NOT NULL,
        component_json BLOB NOT NULL,
        binding_version INTEGER NOT NULL CHECK (binding_version = 1),
        binding_sha256 TEXT NOT NULL CHECK (length(binding_sha256)=64),
        created_at TEXT NOT NULL,
        UNIQUE(work_item_id, binding_sha256)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE approvals (
        id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE RESTRICT,
        binding_sha256 TEXT NOT NULL CHECK (length(binding_sha256)=64),
        decision TEXT NOT NULL CHECK (decision IN ('approved','rejected','withdrawn','invalidated','superseded','consumed')),
        actor_id TEXT NOT NULL,
        decided_at TEXT NOT NULL,
        action_id TEXT NOT NULL UNIQUE,
        UNIQUE(revision_id, binding_sha256, decision, action_id)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE publications (
        id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE RESTRICT,
        approval_id TEXT NOT NULL REFERENCES approvals(id) ON DELETE RESTRICT,
        platform TEXT NOT NULL CHECK (platform IN ('x','truth_social')),
        owned_account_id TEXT NOT NULL REFERENCES owned_accounts(id) ON DELETE RESTRICT,
        external_post_id TEXT NOT NULL,
        canonical_url TEXT NOT NULL,
        verification_state TEXT NOT NULL CHECK (verification_state IN ('owner_confirmed','platform_observed','verified_match','verified_mismatch','deleted_or_inaccessible')),
        observed_at TEXT NOT NULL,
        UNIQUE(platform, owned_account_id, external_post_id),
        UNIQUE(approval_id)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE metric_snapshots (
        id TEXT PRIMARY KEY,
        publication_id TEXT NOT NULL REFERENCES publications(id) ON DELETE RESTRICT,
        observation_method TEXT NOT NULL CHECK (observation_method IN ('manual','api')),
        capture_session_id TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        metric_set_version INTEGER NOT NULL,
        metrics_json BLOB NOT NULL,
        observation_state TEXT NOT NULL CHECK (observation_state IN ('observed_value','observed_empty','not_requested','not_returned','unavailable','withheld','malformed','errored','unsupported')),
        corrects_snapshot_id TEXT REFERENCES metric_snapshots(id) ON DELETE RESTRICT,
        UNIQUE(publication_id, observation_method, capture_session_id)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE operation_keys (
        operation_type TEXT NOT NULL,
        operation_key TEXT NOT NULL,
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
        result_ref TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(operation_type, operation_key)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE audit_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        occurred_at TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        record_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        payload_json BLOB NOT NULL,
        previous_chain_sha256 TEXT,
        event_sha256 TEXT NOT NULL CHECK (length(event_sha256)=64),
        chain_sha256 TEXT NOT NULL CHECK (length(chain_sha256)=64)
    ) STRICT;
    """)
    op.execute("""
    CREATE TRIGGER audit_events_no_update
    BEFORE UPDATE ON audit_events BEGIN
        SELECT RAISE(ABORT, 'audit events are append-only');
    END;
    """)
    op.execute("""
    CREATE TRIGGER audit_events_no_delete
    BEFORE DELETE ON audit_events BEGIN
        SELECT RAISE(ABORT, 'audit events are append-only');
    END;
    """)


def downgrade() -> None:
    for name in [
        "audit_events", "operation_keys", "metric_snapshots", "publications",
        "approvals", "revisions", "evidence_refs", "work_items", "owned_accounts"
    ]:
        op.execute(f"DROP TABLE IF EXISTS {name}")
