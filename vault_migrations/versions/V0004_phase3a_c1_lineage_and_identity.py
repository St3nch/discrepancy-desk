"""Correct Phase 3A execution/package/document lineage and tuple identity.

Revision ID: V0004
Revises: V0003
"""
from alembic import op

revision = "V0004"
down_revision = "V0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    invalid_chain = connection.exec_driver_sql(
        """
        SELECT dv.id
        FROM document_versions dv
        JOIN normalized_packages np
          ON np.vault_account_id=dv.vault_account_id
         AND np.id=dv.normalized_package_id
        JOIN parser_executions pe
          ON pe.vault_account_id=dv.vault_account_id
         AND pe.id=dv.parser_execution_id
        WHERE np.parser_execution_id!=dv.parser_execution_id
           OR pe.input_sha256!=dv.source_artifact_sha256
        LIMIT 1
        """
    ).fetchone()
    if invalid_chain is not None:
        raise RuntimeError("refusing V0004 upgrade with inconsistent package/document lineage")

    duplicate_ordinal = connection.exec_driver_sql(
        """
        SELECT pe.acquisition_artifact_link_id, dv.version_ordinal
        FROM document_versions dv
        JOIN parser_executions pe
          ON pe.vault_account_id=dv.vault_account_id
         AND pe.id=dv.parser_execution_id
        GROUP BY dv.vault_account_id, pe.acquisition_artifact_link_id, dv.version_ordinal
        HAVING count(*)>1
        LIMIT 1
        """
    ).fetchone()
    if duplicate_ordinal is not None:
        raise RuntimeError("refusing V0004 upgrade with duplicate artifact-lineage version ordinal")

    op.execute(
        """
        CREATE TABLE parser_execution_package_links (
            vault_account_id TEXT NOT NULL,
            parser_execution_id TEXT NOT NULL,
            normalized_package_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(vault_account_id, parser_execution_id),
            UNIQUE(vault_account_id, parser_execution_id, normalized_package_id),
            FOREIGN KEY(vault_account_id, parser_execution_id)
                REFERENCES parser_executions(vault_account_id, id) ON DELETE RESTRICT,
            FOREIGN KEY(vault_account_id, normalized_package_id)
                REFERENCES normalized_packages(vault_account_id, id) ON DELETE RESTRICT
        ) STRICT;
        """
    )
    op.execute(
        """
        INSERT INTO parser_execution_package_links
        (vault_account_id, parser_execution_id, normalized_package_id, created_at)
        SELECT vault_account_id, parser_execution_id, id, created_at
        FROM normalized_packages
        """
    )
    op.execute(
        """
        CREATE TRIGGER parser_execution_package_links_no_update
        BEFORE UPDATE ON parser_execution_package_links BEGIN
            SELECT RAISE(ABORT, 'parser_execution_package_links is append-only');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER parser_execution_package_links_no_delete
        BEFORE DELETE ON parser_execution_package_links BEGIN
            SELECT RAISE(ABORT, 'parser_execution_package_links is append-only');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER parser_execution_package_links_exact_tuple_guard
        BEFORE INSERT ON parser_execution_package_links
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1
                FROM parser_executions candidate
                JOIN normalized_packages package
                  ON package.vault_account_id=NEW.vault_account_id
                 AND package.id=NEW.normalized_package_id
                JOIN parser_executions origin
                  ON origin.vault_account_id=package.vault_account_id
                 AND origin.id=package.parser_execution_id
                WHERE candidate.vault_account_id=NEW.vault_account_id
                  AND candidate.id=NEW.parser_execution_id
                  AND candidate.state IN ('succeeded','succeeded_with_warnings')
                  AND candidate.package_sha256=package.package_sha256
                  AND candidate.input_sha256=origin.input_sha256
                  AND candidate.parser_definition_id=origin.parser_definition_id
                  AND candidate.parser_configuration_version_id=origin.parser_configuration_version_id
                  AND candidate.parser_admission_version_id=origin.parser_admission_version_id
                  AND candidate.security_profile_id=origin.security_profile_id
            ) THEN RAISE(ABORT, 'package reuse requires an exact successful parser tuple and input') END;
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER normalized_packages_origin_link
        AFTER INSERT ON normalized_packages
        BEGIN
            INSERT INTO parser_execution_package_links
            (vault_account_id, parser_execution_id, normalized_package_id, created_at)
            VALUES (NEW.vault_account_id, NEW.parser_execution_id, NEW.id, NEW.created_at);
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_versions_exact_lineage_guard
        BEFORE INSERT ON document_versions
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1
                FROM parser_execution_package_links link
                JOIN parser_executions execution
                  ON execution.vault_account_id=link.vault_account_id
                 AND execution.id=link.parser_execution_id
                WHERE link.vault_account_id=NEW.vault_account_id
                  AND link.parser_execution_id=NEW.parser_execution_id
                  AND link.normalized_package_id=NEW.normalized_package_id
                  AND execution.input_sha256=NEW.source_artifact_sha256
            ) THEN RAISE(ABORT, 'document version requires exact execution/package/artifact lineage') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1
                FROM document_versions prior
                JOIN parser_executions prior_execution
                  ON prior_execution.vault_account_id=prior.vault_account_id
                 AND prior_execution.id=prior.parser_execution_id
                JOIN parser_executions new_execution
                  ON new_execution.vault_account_id=NEW.vault_account_id
                 AND new_execution.id=NEW.parser_execution_id
                WHERE prior.vault_account_id=NEW.vault_account_id
                  AND prior_execution.acquisition_artifact_link_id=
                      new_execution.acquisition_artifact_link_id
                  AND prior.version_ordinal=NEW.version_ordinal
            ) THEN RAISE(ABORT, 'document version ordinal already exists in artifact lineage') END;
        END;
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    reused = connection.exec_driver_sql(
        """
        SELECT 1
        FROM parser_execution_package_links link
        JOIN normalized_packages package
          ON package.vault_account_id=link.vault_account_id
         AND package.id=link.normalized_package_id
        WHERE link.parser_execution_id!=package.parser_execution_id
        LIMIT 1
        """
    ).fetchone()
    current_profile = connection.exec_driver_sql(
        """
        SELECT 1 FROM parser_definitions
        WHERE security_profile_id='m06a.parser-worker.windows.v2'
        LIMIT 1
        """
    ).fetchone()
    if reused is not None or current_profile is not None:
        raise RuntimeError("refusing to downgrade V0004 with governed Phase 3A-C1 authority")

    op.execute("DROP TRIGGER IF EXISTS document_versions_exact_lineage_guard")
    op.execute("DROP TRIGGER IF EXISTS normalized_packages_origin_link")
    op.execute("DROP TRIGGER IF EXISTS parser_execution_package_links_exact_tuple_guard")
    op.execute("DROP TRIGGER IF EXISTS parser_execution_package_links_no_delete")
    op.execute("DROP TRIGGER IF EXISTS parser_execution_package_links_no_update")
    op.execute("DROP TABLE parser_execution_package_links")
