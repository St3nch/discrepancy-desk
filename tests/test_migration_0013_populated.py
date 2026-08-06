"""Populated-database migration test for 0013 (ticket 10 review).

Why this file exists
--------------------
Ordinary tests upgrade an *empty* database to head. That never fires foreign-key
enforcement on DROP TABLE, so rebuilds of referenced tables look green until
they hit real data. 0013 originally rebuilt ``runs`` and failed on a populated
0012 database (captures, claims, suspensions, open questions, low-confidence
all reference runs).

This test deliberately:

1. Upgrades only to 0012 (pre-coverage).
2. Inserts representative run-dependent rows by hand (no service layer — schema
   is the 0012 shape, without coverage_dimension).
3. Upgrades to head and asserts the upgrade succeeds, every dependent row
   survives, legacy coverage_dimension is NULL, and those runs contribute to no
   coverage stage reading.
4. Downgrades 0013 → 0012 against the same populated DB and re-upgrades, so the
   FK-safe rebuild helper is exercised both ways.

Do not "simplify" this back to an empty upgrade path — that was the gap.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from desk.db.session import connection_scope
from desk.service.coverage import get_case_coverage
from desk.service.models import GetCaseCoverageInput

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_cfg(database_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.resolve()}")
    return cfg


def test_0013_upgrade_and_downgrade_on_populated_0012_db(tmp_path: Path) -> None:
    db_path = tmp_path / "populated_0012.db"
    cfg = _alembic_cfg(db_path)

    command.upgrade(cfg, "0012_unsupported")

    engine = create_engine(f"sqlite:///{db_path.resolve()}")
    # FK on — same as production engine.
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(
            text(
                "INSERT INTO cases (id, title, created_at) "
                "VALUES (1, 'Legacy', '2026-01-01T00:00:00+00:00')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO runs (
                    id, case_id, status, question, scope, rubric_version, rubric_text,
                    capture_budget, created_at, updated_at
                ) VALUES (
                    1, 1, 'complete', 'Legacy Q?', 'scope', 'v1', 'rubric',
                    5, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO captures (
                    id, run_id, case_id, url, sha256, content_type, byte_size,
                    vault_relpath, status, created_at
                ) VALUES (
                    1, 1, 1, 'https://example.com/legacy', 'abc', 'text/html', 10,
                    'raw/ab/abc', 'cited', '2026-01-01T00:00:00+00:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO claims (
                    id, case_id, run_id, proposition, confirmation_status,
                    source_basis, corroboration, certainty, posture, qualification,
                    publication_risk, rubric_version, created_at
                ) VALUES (
                    1, 1, 1, 'Legacy proposition.', 'unconfirmed',
                    'contemporaneous_report', 'single_source', 'probable',
                    'factual_assertion', '', 'not_applicable', 'v1',
                    '2026-01-01T00:00:00+00:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO run_suspensions (
                    id, run_id, ordinal, question, uncertainty, default_action,
                    suspended_at, human_answer, answered_at
                ) VALUES (
                    1, 1, 1, 'Was this answered?', 'A vs B', 'A',
                    '2026-01-01T00:00:00+00:00', 'A', '2026-01-01T01:00:00+00:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO open_questions (
                    id, case_id, introduced_by_run_id, source_run_question, ordinal,
                    proposed_text, rationale, proposed_scope, agenda_decision,
                    disposition, settled_text, settled_scope, created_at, decided_at
                ) VALUES (
                    1, 1, 1, 'Legacy Q?', 1,
                    'What next?', 'Because', 'scope', 'pending',
                    NULL, NULL, NULL, '2026-01-01T00:00:00+00:00', NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO run_low_confidence (id, run_id, ordinal, statement)
                VALUES (1, 1, 1, 'Felt thin')
                """
            )
        )

    # Upgrade to head (0013+) against populated data — must not FK-fail.
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        dim = conn.execute(text("SELECT coverage_dimension FROM runs WHERE id = 1")).scalar_one()
        assert dim is None

        assert conn.execute(text("SELECT COUNT(*) FROM captures")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM claims")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM run_suspensions")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM open_questions")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM run_low_confidence")).scalar_one() == 1
        assert (
            conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='coverage_attestations'"
                )
            ).scalar_one()
            == "coverage_attestations"
        )

    # Legacy NULL dimension contributes to no stage (service seam on upgraded DB).
    from desk.db.engine import create_db_engine

    desk_engine = create_db_engine(db_path)
    try:
        with connection_scope(desk_engine) as conn:
            gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=1))
            of = next(s for s in gauge.stages if s.stage == "official_foundation")
            assert of.reading == "unworked"
            assert "0 completed run" in " ".join(of.signals)
    finally:
        desk_engine.dispose()

    # Downgrade 0013 and re-upgrade — FK-safe rebuild must hold populated data.
    command.downgrade(cfg, "0012_unsupported")
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(runs)")).fetchall()}
        assert "coverage_dimension" not in cols
        assert conn.execute(text("SELECT COUNT(*) FROM claims")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM run_low_confidence")).scalar_one() == 1
        assert (
            conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='coverage_attestations'"
                )
            ).scalar_one_or_none()
            is None
        )

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        dim = conn.execute(text("SELECT coverage_dimension FROM runs WHERE id = 1")).scalar_one()
        assert dim is None
        assert conn.execute(text("SELECT COUNT(*) FROM claims")).scalar_one() == 1

    engine.dispose()
