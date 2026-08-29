"""Structural guards on the SQL the runner will execute.

These protect the specific corrections the Steward reconciliation made. A later
"simplification" that reintroduces the harness's original shapes would silently
weaken the proof, so each correction is pinned here.
"""

from __future__ import annotations

import ast
import inspect

from tools.postgres_foundation_proofs import databases, proof_a, proof_b, proof_c, sql


def test_advisory_lock_is_identified_by_the_documented_representation():
    # Reconciliation section 2.1: objsubid = 1 plus the reassembled key.
    # Matching on objid alone is explicitly forbidden.
    assert "l.objsubid = 1" in sql.OBSERVER_ADVISORY_LOCKS
    assert (
        "((l.classid::bigint << 32) | l.objid::bigint) = %(lock_key)s"
        in sql.OBSERVER_ADVISORY_LOCKS
    )
    assert "objid = 90201001" not in sql.OBSERVER_ADVISORY_LOCKS


def test_observer_scopes_locks_to_the_proof_database_and_known_pids():
    assert "l.database = (SELECT oid FROM pg_database WHERE datname = current_database())" in (
        sql.OBSERVER_ADVISORY_LOCKS
    )
    assert "l.pid = ANY(%(pids)s::int[])" in sql.OBSERVER_ADVISORY_LOCKS


def test_observer_whitelists_columns_rather_than_selecting_everything():
    # pg_stat_activity rows must never be splatted into the report.
    assert "SELECT *" not in sql.OBSERVER_ADVISORY_LOCKS
    assert "a.query" not in sql.OBSERVER_ADVISORY_LOCKS


def test_blocking_pids_is_used_to_identify_the_blocker():
    assert "pg_blocking_pids(%(pid)s)" in sql.OBSERVER_BLOCKING_PIDS


def test_sequence_state_is_observed_directly():
    assert "pg_sequence_last_value" in sql.OBSERVER_SEQUENCE_LAST_VALUE


def _executable_string_literals(module) -> list[str]:
    """Every string constant in a module except its docstrings.

    Docstrings are prose about the code; only the remaining literals can reach
    PostgreSQL, so those are what a SQL guard should inspect.
    """
    tree = ast.parse(inspect.getsource(module))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]


def test_pg_sleep_is_not_used_as_proof_of_blocking():
    # Reconciliation section 2.1: pg_sleep(8) is not normative for the
    # programmatic runner and must not be used as proof of blocking.
    for name, value in vars(sql).items():
        if isinstance(value, str) and not name.startswith("__"):
            assert "pg_sleep" not in value, name
    for literal in _executable_string_literals(proof_a):
        assert "pg_sleep" not in literal


def test_all_executed_sql_lives_in_the_sql_module():
    # Keeps "SQL execution is explicit and reviewable" true by construction:
    # a reviewer diffs sql.py against the harness and has seen everything.
    for module in (proof_a, proof_b, proof_c):
        for literal in _executable_string_literals(module):
            upper = literal.upper()
            assert not any(
                upper.startswith(verb)
                for verb in ("SELECT ", "INSERT ", "CREATE ", "DROP ", "UPDATE ", "DELETE ")
            ), (module.__name__, literal[:60])


def test_boundary_is_parameter_bound_not_psql_interpolated():
    for query in (sql.PROOF_B_BOUNDARY_QUERY, sql.PROOF_B_CLUSTER_QUERY):
        assert "%(boundary)s" in query
        assert ":B" not in query
        assert "\\set" not in query


def test_both_proof_b_queries_share_the_same_ctes():
    # Reconciliation section 3 requires the cluster projection to run over the
    # same operative/positive_edge/reach CTEs.
    for cte in ("operative AS", "positive_edge AS", "reach(src, dst) AS", "conflict AS"):
        assert cte in sql.PROOF_B_BOUNDARY_QUERY
        assert cte in sql.PROOF_B_CLUSTER_QUERY


def test_cluster_projection_matches_the_pinned_shape():
    assert "SELECT DISTINCT src, dst" in sql.PROOF_B_CLUSTER_QUERY
    assert "WHERE src < dst" in sql.PROOF_B_CLUSTER_QUERY
    assert "ORDER BY src, dst" in sql.PROOF_B_CLUSTER_QUERY


def test_recursive_closure_deduplicates_so_cycles_terminate():
    # UNION, not UNION ALL, inside reach(): the seed data is cyclic.
    reach = sql.PROOF_B_BOUNDARY_QUERY.split("reach(src, dst) AS")[1].split("conflict AS")[0]
    assert "UNION\n" in reach
    assert "UNION ALL" not in reach


def test_proof_c_view_is_a_union_all_traversal_surface():
    view = [s for s in sql.PROOF_C_SETUP if "CREATE VIEW" in s][0]
    assert "UNION ALL" in view
    assert "provenance_edge_v" in view


def test_proof_c_reverse_indexes_exist_on_both_typed_tables():
    setup = "\n".join(sql.PROOF_C_SETUP)
    assert "claim_version_observation_basis_reverse_idx" in setup
    assert "claim_version_decision_dependency_reverse_idx" in setup


def test_proof_c_relation_vocabularies_are_default_deny_checks():
    setup = "\n".join(sql.PROOF_C_SETUP)
    assert "CHECK (relation_kind IN ('supports', 'contradicts'))" in setup
    assert "CHECK (dependency_kind IN ('identity_resolution', 'claim_posture'))" in setup


def test_proof_a_sequence_is_created_with_cache_one():
    assert "CREATE SEQUENCE proof.record_admission_order_seq CACHE 1" in sql.PROOF_A_SETUP


def test_every_proof_creates_the_proof_schema():
    for setup in (sql.PROOF_A_SETUP, sql.PROOF_B_SETUP, sql.PROOF_C_SETUP):
        assert "CREATE SCHEMA proof" in setup


def test_proof_databases_are_created_from_the_pristine_template():
    # Reconciliation section 5: TEMPLATE template0, not mutable template1.
    source = inspect.getsource(databases.create_proof_database)
    assert "TEMPLATE template0" in source
    assert "template1" not in source


def test_drop_uses_force_as_a_backstop():
    source = inspect.getsource(databases.drop_proof_database)
    assert "DROP DATABASE IF EXISTS" in source
    assert "WITH (FORCE)" in source


def test_emptiness_check_ignores_system_objects_only():
    assert "pg_catalog" in sql.SELECT_NON_SYSTEM_RELATIONS
    assert "information_schema" in sql.SELECT_NON_SYSTEM_RELATIONS


def test_preflight_uses_the_four_harness_statements():
    assert sql.SELECT_VERSION == "SELECT version()"
    assert sql.SHOW_SERVER_VERSION_NUM == "SHOW server_version_num"
    assert sql.SHOW_SERVER_VERSION == "SHOW server_version"
    assert sql.SHOW_TRACK_COMMIT_TIMESTAMP == "SHOW track_commit_timestamp"


def test_no_sql_constant_references_a_hard_coded_host_or_port():
    # Reconciliation section 8 forbids treating port 5433 as a security boundary.
    for name, value in vars(sql).items():
        if isinstance(value, str) and not name.startswith("__"):
            assert "5433" not in value, name
            assert "127.0.0.1" not in value, name
