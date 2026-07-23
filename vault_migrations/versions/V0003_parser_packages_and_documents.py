"""Create M06-A Phase 3A parser, package, and document foundation.

Revision ID: V0003
Revises: V0002
"""
from alembic import op

revision = "V0003"
down_revision = "V0002"
branch_labels = None
depends_on = None

APPEND_ONLY_TABLES = (
    "parser_definitions",
    "parser_configuration_versions",
    "parser_admission_versions",
    "normalized_packages",
    "document_versions",
    "elements",
    "regions",
)


def upgrade() -> None:
    op.execute("""
    CREATE TABLE parser_definitions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        format_id TEXT NOT NULL,
        implementation_kind TEXT NOT NULL CHECK (
            implementation_kind IN ('stdlib','internal','external_python','native')
        ),
        implementation_entrypoint TEXT NOT NULL,
        implementation_version TEXT NOT NULL,
        implementation_sha256 TEXT NOT NULL CHECK (
            length(implementation_sha256)=64 AND implementation_sha256=lower(implementation_sha256)
        ),
        resource_manifest_sha256 TEXT NOT NULL CHECK (
            length(resource_manifest_sha256)=64 AND resource_manifest_sha256=lower(resource_manifest_sha256)
        ),
        dependency_lock_sha256 TEXT NOT NULL CHECK (
            length(dependency_lock_sha256)=64 AND dependency_lock_sha256=lower(dependency_lock_sha256)
        ),
        license_id TEXT NOT NULL,
        package_schema_version TEXT NOT NULL,
        deterministic_contract_version TEXT NOT NULL,
        security_profile_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by_actor_id TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE parser_configuration_versions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        parser_definition_id TEXT NOT NULL,
        canonical_config_json BLOB NOT NULL,
        config_sha256 TEXT NOT NULL CHECK (
            length(config_sha256)=64 AND config_sha256=lower(config_sha256)
        ),
        size_limit_bytes INTEGER NOT NULL CHECK (size_limit_bytes>0),
        depth_limit INTEGER CHECK (depth_limit IS NULL OR depth_limit>0),
        element_limit INTEGER NOT NULL CHECK (element_limit>0),
        line_limit INTEGER CHECK (line_limit IS NULL OR line_limit>0),
        maximum_line_bytes INTEGER CHECK (maximum_line_bytes IS NULL OR maximum_line_bytes>0),
        warning_policy_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by_actor_id TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, config_sha256),
        FOREIGN KEY(vault_account_id, parser_definition_id)
            REFERENCES parser_definitions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE parser_admission_versions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        parser_definition_id TEXT NOT NULL,
        parser_configuration_version_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (
            state IN ('candidate','under_test','owner_admitted','suspended','revoked','retired','prohibited')
        ),
        fixture_manifest_sha256 TEXT NOT NULL CHECK (
            length(fixture_manifest_sha256)=64 AND fixture_manifest_sha256=lower(fixture_manifest_sha256)
        ),
        focused_test_evidence_sha256 TEXT NOT NULL CHECK (
            length(focused_test_evidence_sha256)=64 AND focused_test_evidence_sha256=lower(focused_test_evidence_sha256)
        ),
        no_egress_evidence_sha256 TEXT NOT NULL CHECK (
            length(no_egress_evidence_sha256)=64 AND no_egress_evidence_sha256=lower(no_egress_evidence_sha256)
        ),
        packaged_sidecar_evidence_sha256 TEXT NOT NULL CHECK (
            length(packaged_sidecar_evidence_sha256)=64 AND packaged_sidecar_evidence_sha256=lower(packaged_sidecar_evidence_sha256)
        ),
        dependency_lock_sha256 TEXT NOT NULL CHECK (
            length(dependency_lock_sha256)=64 AND dependency_lock_sha256=lower(dependency_lock_sha256)
        ),
        admitted_by_actor_id TEXT,
        admitted_at TEXT,
        supersedes_admission_id TEXT,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by_actor_id TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        CHECK (supersedes_admission_id IS NULL OR supersedes_admission_id!=id),
        CHECK (
            (state='owner_admitted' AND admitted_by_actor_id IS NOT NULL AND admitted_at IS NOT NULL)
            OR (state!='owner_admitted' AND admitted_by_actor_id IS NULL AND admitted_at IS NULL)
        ),
        FOREIGN KEY(vault_account_id, parser_definition_id)
            REFERENCES parser_definitions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, parser_configuration_version_id)
            REFERENCES parser_configuration_versions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, admitted_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, supersedes_admission_id)
            REFERENCES parser_admission_versions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, created_by_actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TRIGGER parser_owner_admission_human_guard
    BEFORE INSERT ON parser_admission_versions
    WHEN NEW.state='owner_admitted'
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM actors
            WHERE vault_account_id=NEW.vault_account_id
              AND id=NEW.admitted_by_actor_id
              AND actor_class='human'
              AND status='active'
              AND (instr(',' || authority_profile || ',', ',vault_admin,')>0
                   OR instr(',' || authority_profile || ',', ',*,')>0)
        ) THEN RAISE(ABORT, 'owner admission requires an active verified human actor') END;
    END;
    """)
    op.execute("""
    CREATE TABLE parser_executions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        vault_instance_id TEXT NOT NULL,
        acquisition_artifact_link_id TEXT NOT NULL,
        parser_definition_id TEXT NOT NULL,
        parser_configuration_version_id TEXT NOT NULL,
        parser_admission_version_id TEXT NOT NULL,
        security_profile_id TEXT NOT NULL,
        input_sha256 TEXT NOT NULL CHECK (length(input_sha256)=64),
        input_size_bytes INTEGER NOT NULL CHECK (input_size_bytes>=0),
        state TEXT NOT NULL CHECK (state IN ('started','succeeded','succeeded_with_warnings','failed')),
        terminal_outcome TEXT CHECK (
            terminal_outcome IS NULL OR terminal_outcome IN (
                'encoding_failure','limit_exceeded','malformed_input','partial_output_failure',
                'security_boundary_violation','determinism_failure','packaging_mismatch',
                'internal_error','success','success_with_warnings'
            )
        ),
        warning_codes_json BLOB NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        worker_receipt_sha256 TEXT CHECK (worker_receipt_sha256 IS NULL OR length(worker_receipt_sha256)=64),
        package_sha256 TEXT CHECK (package_sha256 IS NULL OR length(package_sha256)=64),
        error_code TEXT,
        operation_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, operation_id),
        CHECK (
            (state='started' AND terminal_outcome IS NULL AND finished_at IS NULL
             AND worker_receipt_sha256 IS NULL AND package_sha256 IS NULL AND error_code IS NULL)
            OR (state IN ('succeeded','succeeded_with_warnings')
                AND terminal_outcome IN ('success','success_with_warnings')
                AND finished_at IS NOT NULL AND worker_receipt_sha256 IS NOT NULL
                AND package_sha256 IS NOT NULL AND error_code IS NULL)
            OR (state='failed' AND terminal_outcome IS NOT NULL
                AND terminal_outcome NOT IN ('success','success_with_warnings')
                AND finished_at IS NOT NULL AND worker_receipt_sha256 IS NOT NULL
                AND package_sha256 IS NULL AND error_code IS NOT NULL)
        ),
        FOREIGN KEY(vault_account_id, acquisition_artifact_link_id)
            REFERENCES acquisition_artifact_links(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, parser_definition_id)
            REFERENCES parser_definitions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, parser_configuration_version_id)
            REFERENCES parser_configuration_versions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, parser_admission_version_id)
            REFERENCES parser_admission_versions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE normalized_packages (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        parser_execution_id TEXT NOT NULL,
        package_schema_version TEXT NOT NULL,
        package_sha256 TEXT NOT NULL CHECK (length(package_sha256)=64),
        byte_size INTEGER NOT NULL CHECK (byte_size>=0),
        storage_relative_path TEXT NOT NULL,
        coverage_sha256 TEXT NOT NULL CHECK (length(coverage_sha256)=64),
        warning_codes_json BLOB NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('current','superseded','quarantined')),
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, parser_execution_id),
        UNIQUE(vault_account_id, storage_relative_path),
        FOREIGN KEY(vault_account_id, parser_execution_id)
            REFERENCES parser_executions(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE document_versions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        normalized_package_id TEXT NOT NULL,
        source_artifact_sha256 TEXT NOT NULL CHECK (length(source_artifact_sha256)=64),
        parser_execution_id TEXT NOT NULL,
        version_ordinal INTEGER NOT NULL CHECK (version_ordinal>0),
        state TEXT NOT NULL CHECK (state IN ('current','superseded','withdrawn','quarantined')),
        created_at TEXT NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, parser_execution_id, version_ordinal),
        FOREIGN KEY(vault_account_id, normalized_package_id)
            REFERENCES normalized_packages(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, parser_execution_id)
            REFERENCES parser_executions(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE elements (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        document_version_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal>=0),
        element_kind TEXT NOT NULL,
        source_locator_json BLOB NOT NULL,
        raw_text TEXT NOT NULL,
        normalized_text TEXT NOT NULL,
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
        warning_codes_json BLOB NOT NULL,
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, document_version_id, ordinal),
        FOREIGN KEY(vault_account_id, document_version_id)
            REFERENCES document_versions(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE regions (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        document_version_id TEXT NOT NULL,
        element_id TEXT,
        ordinal INTEGER NOT NULL CHECK (ordinal>=0),
        region_kind TEXT NOT NULL,
        source_locator_json BLOB NOT NULL,
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
        UNIQUE(vault_account_id, id),
        UNIQUE(vault_account_id, document_version_id, ordinal),
        FOREIGN KEY(vault_account_id, document_version_id)
            REFERENCES document_versions(vault_account_id, id) ON DELETE RESTRICT,
        FOREIGN KEY(vault_account_id, element_id)
            REFERENCES elements(vault_account_id, id) ON DELETE RESTRICT
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

    op.execute("""
    CREATE TRIGGER parser_executions_no_delete
    BEFORE DELETE ON parser_executions BEGIN
        SELECT RAISE(ABORT, 'parser_executions cannot be deleted');
    END;
    """)
    op.execute("""
    CREATE TRIGGER parser_executions_update_guard
    BEFORE UPDATE ON parser_executions
    BEGIN
        SELECT CASE WHEN
            NEW.id!=OLD.id
            OR NEW.vault_account_id!=OLD.vault_account_id
            OR NEW.vault_instance_id!=OLD.vault_instance_id
            OR NEW.acquisition_artifact_link_id!=OLD.acquisition_artifact_link_id
            OR NEW.parser_definition_id!=OLD.parser_definition_id
            OR NEW.parser_configuration_version_id!=OLD.parser_configuration_version_id
            OR NEW.parser_admission_version_id!=OLD.parser_admission_version_id
            OR NEW.security_profile_id!=OLD.security_profile_id
            OR NEW.input_sha256!=OLD.input_sha256
            OR NEW.input_size_bytes!=OLD.input_size_bytes
            OR NEW.started_at!=OLD.started_at
            OR NEW.operation_id!=OLD.operation_id
            OR NEW.actor_id!=OLD.actor_id
            THEN RAISE(ABORT, 'parser execution immutable fields cannot change')
        END;
        SELECT CASE WHEN NOT (
            OLD.state='started'
            AND NEW.state IN ('succeeded','succeeded_with_warnings','failed')
            AND NEW.finished_at IS NOT NULL
            AND NEW.worker_receipt_sha256 IS NOT NULL
        ) THEN RAISE(ABORT, 'illegal parser execution lifecycle update') END;
    END;
    """)


def downgrade() -> None:
    connection = op.get_bind()
    governed = (
        "regions",
        "elements",
        "document_versions",
        "normalized_packages",
        "parser_executions",
        "parser_admission_versions",
        "parser_configuration_versions",
        "parser_definitions",
    )
    for table in governed:
        if connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            raise RuntimeError("refusing to downgrade V0003 with governed Phase 3A rows")
    op.execute("DROP TRIGGER IF EXISTS parser_executions_update_guard")
    op.execute("DROP TRIGGER IF EXISTS parser_executions_no_delete")
    op.execute("DROP TRIGGER IF EXISTS parser_owner_admission_human_guard")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
    for table in governed:
        op.execute(f"DROP TABLE IF EXISTS {table}")
