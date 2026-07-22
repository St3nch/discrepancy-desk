"""Create M06-A Phase 2 ingestion, artifact, policy, and backup foundation.

Revision ID: V0002
Revises: V0001
"""
from alembic import op

revision = "V0002"
down_revision = "V0001"
branch_labels = None
depends_on = None

APPEND_ONLY_TABLES = (
    "sources",
    "source_items",
    "occurrences",
    "observations",
    "rights_retention_versions",
    "intake_rejection_receipts",
    "artifact_objects",
    "acquisition_artifact_links",
    "artifact_policy_bindings",
    "backup_generation_files",
)

MUTABLE_NO_DELETE_TABLES = (
    "acquisitions",
    "intake_upload_authorizations",
    "backup_generations",
)


def upgrade() -> None:
    op.execute("""
    CREATE TABLE sources (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        source_kind TEXT NOT NULL CHECK (source_kind IN ('manual_file','manual_locator')),
        platform_label TEXT,
        display_label TEXT NOT NULL,
        created_by_actor_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE source_items (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        item_locator TEXT,
        item_state TEXT NOT NULL CHECK (item_state IN ('current','withdrawn')),
        created_by_actor_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        FOREIGN KEY(vault_account_id, source_id)
            REFERENCES sources(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE occurrences (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        source_item_id TEXT NOT NULL,
        occurrence_kind TEXT NOT NULL CHECK (occurrence_kind IN ('manual_selection','manual_locator')),
        occurred_at TEXT,
        created_by_actor_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        FOREIGN KEY(vault_account_id, source_item_id)
            REFERENCES source_items(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE observations (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        occurrence_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        observation_method TEXT NOT NULL CHECK (observation_method IN ('human_file_selection','human_locator_entry')),
        observed_at TEXT NOT NULL,
        observation_state TEXT NOT NULL CHECK (observation_state IN ('observed','locator_only','blocked')),
        note_text TEXT,
        receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256)=64),
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        FOREIGN KEY(vault_account_id, occurrence_id)
            REFERENCES occurrences(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE rights_retention_versions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        retention_eligible TEXT NOT NULL CHECK (retention_eligible IN ('allow','deny','unknown')),
        retention_deadline TEXT,
        internal_retrieval_eligible TEXT NOT NULL CHECK (internal_retrieval_eligible IN ('allow','deny','unknown')),
        context_run_eligible TEXT NOT NULL CHECK (context_run_eligible IN ('allow','deny','unknown')),
        export_eligible TEXT NOT NULL CHECK (export_eligible IN ('allow','deny','unknown')),
        internal_projection_eligible TEXT NOT NULL CHECK (internal_projection_eligible IN ('allow','deny','unknown')),
        public_projection_eligible TEXT NOT NULL CHECK (public_projection_eligible IN ('allow','deny','unknown')),
        quotation_redistribution_eligible TEXT NOT NULL CHECK (quotation_redistribution_eligible IN ('allow','deny','unknown')),
        policy_basis TEXT NOT NULL,
        human_classification_note TEXT NOT NULL,
        reviewed_by_actor_id TEXT NOT NULL,
        reviewed_at TEXT NOT NULL,
        CHECK (retention_eligible!='allow' OR retention_deadline IS NULL),
        UNIQUE(vault_account_id, id),
        FOREIGN KEY(vault_account_id, reviewed_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE intake_rejection_receipts (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        operation_key TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        attempted_source_kind TEXT NOT NULL CHECK (attempted_source_kind IN ('manual_file','manual_locator')),
        descriptor_class TEXT NOT NULL CHECK (descriptor_class IN ('file','locator')),
        retention_classification TEXT NOT NULL CHECK (retention_classification IN ('timed_deletion_required','unknown','missing','contradictory')),
        policy_basis_reference TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        client_nonce TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        UNIQUE(vault_account_id, operation_key),
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE acquisitions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        observation_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('started','finalized','interrupted','reconciled')),
        outcome TEXT CHECK (outcome IS NULL OR outcome IN ('succeeded','failed','rejected','quarantined','no_artifact')),
        operation_key TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finalized_at TEXT,
        error_class TEXT,
        error_code TEXT,
        supplied_filename TEXT,
        supplied_media_type TEXT,
        rights_retention_version_id TEXT NOT NULL,
        receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256)=64),
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, operation_key),
        CHECK (
            (lifecycle_state='started' AND outcome IS NULL AND finalized_at IS NULL)
            OR (lifecycle_state IN ('finalized','interrupted','reconciled') AND outcome IS NOT NULL AND finalized_at IS NOT NULL)
        ),
        FOREIGN KEY(vault_account_id, observation_id)
            REFERENCES observations(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, rights_retention_version_id)
            REFERENCES rights_retention_versions(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE intake_upload_authorizations (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        acquisition_id TEXT NOT NULL,
        operation_key TEXT NOT NULL,
        max_bytes INTEGER NOT NULL CHECK (max_bytes>0),
        issued_at TEXT NOT NULL,
        consumed_at TEXT,
        UNIQUE(vault_account_id, acquisition_id),
        UNIQUE(vault_account_id, operation_key),
        FOREIGN KEY(vault_account_id, acquisition_id)
            REFERENCES acquisitions(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE artifact_objects (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        sha256 TEXT NOT NULL CHECK (length(sha256)=64),
        byte_size INTEGER NOT NULL CHECK (byte_size>=0),
        storage_relative_path TEXT NOT NULL,
        media_type_observed TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, sha256),
        UNIQUE(vault_account_id, storage_relative_path)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE acquisition_artifact_links (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        acquisition_id TEXT NOT NULL,
        artifact_object_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('original','supporting')),
        supplied_filename TEXT,
        supplied_media_type TEXT,
        rights_retention_version_id TEXT NOT NULL,
        receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256)=64),
        linked_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, acquisition_id, artifact_object_id, role),
        FOREIGN KEY(vault_account_id, acquisition_id)
            REFERENCES acquisitions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, artifact_object_id)
            REFERENCES artifact_objects(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, rights_retention_version_id)
            REFERENCES rights_retention_versions(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE artifact_policy_bindings (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        artifact_object_id TEXT NOT NULL,
        rights_retention_version_id TEXT NOT NULL,
        binding_state TEXT NOT NULL CHECK (binding_state IN ('current','superseded','blocked')),
        supersedes_binding_id TEXT,
        created_by_actor_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        CHECK (supersedes_binding_id IS NULL OR supersedes_binding_id!=id),
        FOREIGN KEY(vault_account_id, artifact_object_id)
            REFERENCES artifact_objects(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, rights_retention_version_id)
            REFERENCES rights_retention_versions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, supersedes_binding_id)
            REFERENCES artifact_policy_bindings(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TRIGGER artifact_policy_binding_lineage_guard
    BEFORE INSERT ON artifact_policy_bindings
    WHEN NEW.binding_state='current'
    BEGIN
        SELECT CASE
            WHEN EXISTS (
                SELECT 1 FROM artifact_policy_bindings current_binding
                WHERE current_binding.vault_account_id=NEW.vault_account_id
                  AND current_binding.artifact_object_id=NEW.artifact_object_id
                  AND current_binding.binding_state='current'
                  AND NOT EXISTS (
                      SELECT 1 FROM artifact_policy_bindings successor
                      WHERE successor.vault_account_id=current_binding.vault_account_id
                        AND successor.supersedes_binding_id=current_binding.id
                  )
            )
            AND NEW.supersedes_binding_id IS NULL
            THEN RAISE(ABORT, 'current artifact policy binding must supersede the current leaf')
        END;
        SELECT CASE
            WHEN NEW.supersedes_binding_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM artifact_policy_bindings current_binding
                WHERE current_binding.vault_account_id=NEW.vault_account_id
                  AND current_binding.artifact_object_id=NEW.artifact_object_id
                  AND current_binding.id=NEW.supersedes_binding_id
                  AND current_binding.binding_state='current'
                  AND NOT EXISTS (
                      SELECT 1 FROM artifact_policy_bindings successor
                      WHERE successor.vault_account_id=current_binding.vault_account_id
                        AND successor.supersedes_binding_id=current_binding.id
                  )
            )
            THEN RAISE(ABORT, 'artifact policy binding must supersede the current leaf')
        END;
    END;
    """)
    op.execute("""
    CREATE TABLE backup_generations (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        vault_instance_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('started','complete','failed','reconciliation_required','verified')),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        migration_head TEXT NOT NULL,
        application_commit TEXT NOT NULL,
        manifest_sha256 TEXT,
        completion_marker_sha256 TEXT,
        actor_id TEXT NOT NULL,
        failure_code TEXT,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, correlation_id),
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE backup_generation_files (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        file_family TEXT NOT NULL CHECK (file_family IN ('database','object','package','manifest','completion')),
        sha256 TEXT NOT NULL CHECK (length(sha256)=64),
        byte_size INTEGER NOT NULL CHECK (byte_size>=0),
        authority_class TEXT NOT NULL CHECK (authority_class IN ('canonical','derived','receipt')),
        required INTEGER NOT NULL CHECK (required IN (0,1)),
        UNIQUE(vault_account_id, generation_id, relative_path),
        FOREIGN KEY(vault_account_id, generation_id)
            REFERENCES backup_generations(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)

    for table in APPEND_ONLY_TABLES:
        op.execute(f"""
        CREATE TRIGGER {table}_no_update
        BEFORE UPDATE ON {table} BEGIN
            SELECT RAISE(ABORT, '{table} is append-only');
        END;
        """)
        op.execute(f"""
        CREATE TRIGGER {table}_no_delete
        BEFORE DELETE ON {table} BEGIN
            SELECT RAISE(ABORT, '{table} is append-only');
        END;
        """)

    for table in MUTABLE_NO_DELETE_TABLES:
        op.execute(f"""
        CREATE TRIGGER {table}_no_delete
        BEFORE DELETE ON {table} BEGIN
            SELECT RAISE(ABORT, '{table} cannot be deleted');
        END;
        """)

    op.execute("""
    CREATE TRIGGER acquisitions_update_guard
    BEFORE UPDATE ON acquisitions
    BEGIN
        SELECT CASE WHEN
            NEW.id!=OLD.id
            OR NEW.vault_account_id!=OLD.vault_account_id
            OR NEW.observation_id!=OLD.observation_id
            OR NEW.actor_id!=OLD.actor_id
            OR NEW.operation_key!=OLD.operation_key
            OR NEW.correlation_id!=OLD.correlation_id
            OR NEW.started_at!=OLD.started_at
            OR NEW.supplied_filename IS NOT OLD.supplied_filename
            OR NEW.supplied_media_type IS NOT OLD.supplied_media_type
            OR NEW.rights_retention_version_id!=OLD.rights_retention_version_id
            OR NEW.receipt_sha256!=OLD.receipt_sha256
            THEN RAISE(ABORT, 'acquisition immutable fields cannot change')
        END;
        SELECT CASE WHEN NOT (
            OLD.lifecycle_state='started'
            AND OLD.outcome IS NULL
            AND NEW.lifecycle_state IN ('finalized','interrupted','reconciled')
            AND NEW.outcome IS NOT NULL
            AND NEW.finalized_at IS NOT NULL
        ) THEN RAISE(ABORT, 'illegal acquisition lifecycle update') END;
    END;
    """)
    op.execute("""
    CREATE TRIGGER intake_upload_authorizations_update_guard
    BEFORE UPDATE ON intake_upload_authorizations
    BEGIN
        SELECT CASE WHEN
            NEW.id!=OLD.id
            OR NEW.vault_account_id!=OLD.vault_account_id
            OR NEW.acquisition_id!=OLD.acquisition_id
            OR NEW.operation_key!=OLD.operation_key
            OR NEW.max_bytes!=OLD.max_bytes
            OR NEW.issued_at!=OLD.issued_at
            OR OLD.consumed_at IS NOT NULL
            OR NEW.consumed_at IS NULL
            THEN RAISE(ABORT, 'upload authorization update is not permitted')
        END;
    END;
    """)
    op.execute("""
    CREATE TRIGGER backup_generations_update_guard
    BEFORE UPDATE ON backup_generations
    BEGIN
        SELECT CASE WHEN
            NEW.id!=OLD.id
            OR NEW.vault_account_id!=OLD.vault_account_id
            OR NEW.vault_instance_id!=OLD.vault_instance_id
            OR NEW.correlation_id!=OLD.correlation_id
            OR NEW.started_at!=OLD.started_at
            OR NEW.migration_head!=OLD.migration_head
            OR NEW.application_commit!=OLD.application_commit
            OR NEW.actor_id!=OLD.actor_id
            THEN RAISE(ABORT, 'backup generation immutable fields cannot change')
        END;
        SELECT CASE WHEN NOT (
            (OLD.lifecycle_state='started'
             AND NEW.lifecycle_state IN ('complete','failed','reconciliation_required'))
            OR (OLD.lifecycle_state='complete' AND NEW.lifecycle_state='verified')
        ) THEN RAISE(ABORT, 'illegal backup generation lifecycle update') END;
    END;
    """)


def downgrade() -> None:
    connection = op.get_bind()
    governed = (
        "vault_metadata",
        "backup_generation_files",
        "backup_generations",
        "artifact_policy_bindings",
        "acquisition_artifact_links",
        "artifact_objects",
        "intake_upload_authorizations",
        "acquisitions",
        "intake_rejection_receipts",
        "rights_retention_versions",
        "observations",
        "occurrences",
        "source_items",
        "sources",
    )
    phase2_tables = governed[1:]
    for table in governed:
        if connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            raise RuntimeError("refusing to downgrade V0002 with governed Phase 2 rows")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
    for table in MUTABLE_NO_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
    op.execute("DROP TRIGGER IF EXISTS acquisitions_update_guard")
    op.execute("DROP TRIGGER IF EXISTS intake_upload_authorizations_update_guard")
    op.execute("DROP TRIGGER IF EXISTS backup_generations_update_guard")
    op.execute("DROP TRIGGER IF EXISTS artifact_policy_binding_lineage_guard")
    for table in phase2_tables:
        op.execute(f"DROP TABLE IF EXISTS {table}")
