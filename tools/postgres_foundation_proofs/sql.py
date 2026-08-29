"""Every SQL statement this runner executes, in one reviewable place.

The ticket requires that "SQL execution is explicit and reviewable" and that the
runner must not "substitute different data/queries that weaken the harness".
Keeping the statements here as literals means a reviewer can diff this module
against POSTGRESQL-SCRATCH-PROOF-HARNESS-01.md directly.

Binding rules (reconciliation section 6): values and boundaries are
parameter-bound; identifiers are composed with the driver's identifier-quoting
facility at the call site; no DSN-derived value is ever interpolated.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Preflight (harness section 1.3, reconciliation section 5)
# --------------------------------------------------------------------------

SELECT_VERSION = "SELECT version()"
SHOW_SERVER_VERSION_NUM = "SHOW server_version_num"
SHOW_SERVER_VERSION = "SHOW server_version"
SHOW_TRACK_COMMIT_TIMESTAMP = "SHOW track_commit_timestamp"

#: Credential-free connection observations. Reconciliation section 5 permits
#: recording these but forbids claiming they prove the Docker image or the
#: host-network path.
SELECT_SERVER_CONTEXT = """
SELECT current_database() AS current_database,
       current_user       AS current_user,
       inet_server_addr()::text AS inet_server_addr,
       inet_server_port() AS inet_server_port
"""

#: Reconciliation section 5: "starts empty" means no Desk/proof application
#: objects exist before that proof's setup. System and template objects are not
#: prohibited, so only non-system namespaces are inspected.
SELECT_NON_SYSTEM_RELATIONS = """
SELECT n.nspname AS schema_name, c.relname AS relation_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp%'
ORDER BY n.nspname, c.relname
"""

#: Fail closed if the supplied role cannot create and drop proof databases.
#: Reconciliation section 5 forbids a one-database fallback.
SELECT_ROLE_CAPABILITY = """
SELECT rolcreatedb, rolsuper
FROM pg_roles
WHERE rolname = current_user
"""

# --------------------------------------------------------------------------
# Proof A -- admission ordering under concurrency (harness section 2)
# --------------------------------------------------------------------------

#: Harness section 2.1, verbatim.
PROOF_A_SETUP = (
    "CREATE SCHEMA proof",
    "CREATE SEQUENCE proof.record_admission_order_seq CACHE 1",
    """
    CREATE TABLE proof.record_admission (
        admission_order bigint PRIMARY KEY,
        label text NOT NULL,
        allocated_at timestamptz NOT NULL
    )
    """,
)

#: Harness section 2.1: one fixed advisory-lock key for this proof.
PROOF_A_LOCK_KEY = 90201001

SELECT_BACKEND_PID = "SELECT pg_backend_pid() AS backend_pid"

ACQUIRE_ADVISORY_XACT_LOCK = "SELECT pg_advisory_xact_lock(%(lock_key)s)"

SELECT_CLOCK_TIMESTAMP = "SELECT clock_timestamp() AS observed_at"

#: Harness sections 2.2 and 2.3. Only the label is parameter-bound.
PROOF_A_INSERT = """
INSERT INTO proof.record_admission
VALUES (
    nextval('proof.record_admission_order_seq'),
    %(label)s,
    clock_timestamp()
)
RETURNING *
"""

PROOF_A_TABLE_DUMP = (
    "SELECT admission_order, label FROM proof.record_admission ORDER BY admission_order"
)

#: Reconciliation section 2.1: identify the advisory lock using PostgreSQL's
#: documented representation for a single-bigint key -- objsubid = 1 and the
#: key reassembled from the high-order classid and low-order objid. Matching on
#: objid alone is explicitly forbidden. Columns are whitelisted rather than
#: selected with *, so no unexpected column can reach the report.
OBSERVER_ADVISORY_LOCKS = """
SELECT l.pid,
       l.granted,
       a.wait_event_type,
       a.wait_event,
       a.state
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
WHERE l.locktype = 'advisory'
  AND l.objsubid = 1
  AND ((l.classid::bigint << 32) | l.objid::bigint) = %(lock_key)s
  AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND l.pid = ANY(%(pids)s::int[])
ORDER BY l.pid
"""

#: Reconciliation section 2.1: PostgreSQL recommends pg_blocking_pids() to
#: identify blockers.
OBSERVER_BLOCKING_PIDS = "SELECT pg_blocking_pids(%(pid)s) AS blocking_pids"

#: Sequence state is non-transactional, so the observer sees A's allocation
#: while A's transaction is still open. This is the direct evidence that B could
#: not allocate its ordinal while A held the lock.
OBSERVER_SEQUENCE_LAST_VALUE = """
SELECT pg_sequence_last_value('proof.record_admission_order_seq'::regclass) AS last_value
"""

# --------------------------------------------------------------------------
# Proof B -- identity triangle, conflict, repair, historical boundary
# (harness section 3, reconciliation section 3)
# --------------------------------------------------------------------------

#: Harness section 3.1, verbatim.
PROOF_B_SETUP = (
    "CREATE SCHEMA proof",
    """
    CREATE TABLE proof.identity_decision (
        decision_id text PRIMARY KEY,
        admitted_order bigint NOT NULL,
        effect text NOT NULL CHECK (effect IN ('same_identity', 'distinct')),
        entity_a text NOT NULL,
        entity_b text NOT NULL,
        CHECK (entity_a < entity_b)
    )
    """,
    """
    CREATE TABLE proof.identity_supersession (
        new_decision_id text NOT NULL REFERENCES proof.identity_decision(decision_id),
        superseded_decision_id text NOT NULL REFERENCES proof.identity_decision(decision_id),
        PRIMARY KEY (new_decision_id, superseded_decision_id)
    )
    """,
    """
    INSERT INTO proof.identity_decision VALUES
    ('D1', 10, 'same_identity', 'E17', 'E42'),
    ('D2', 11, 'same_identity', 'E42', 'E99'),
    ('D3', 12, 'same_identity', 'E17', 'E99'),
    ('D8', 15, 'distinct',      'E17', 'E42'),
    ('D9', 20, 'distinct',      'E17', 'E42')
    """,
    """
    INSERT INTO proof.identity_supersession VALUES
    ('D9', 'D1'),
    ('D9', 'D3'),
    ('D9', 'D8')
    """,
)

#: Harness section 3.2. The psql ``\\set B`` / ``:B`` notation is illustrative
#: (reconciliation section 3); the programmatic runner binds the boundary as a
#: SQL parameter. The CTE prefix is shared by both Proof B queries so the
#: reconciliation's requirement to "run the same operative, positive_edge, and
#: reach CTEs" is structurally guaranteed rather than maintained by hand.
_PROOF_B_CTES = """
WITH RECURSIVE
operative AS (
    SELECT d.*
    FROM proof.identity_decision d
    WHERE d.admitted_order <= %(boundary)s
      AND NOT EXISTS (
          SELECT 1
          FROM proof.identity_supersession s
          JOIN proof.identity_decision newer
            ON newer.decision_id = s.new_decision_id
          WHERE s.superseded_decision_id = d.decision_id
            AND newer.admitted_order <= %(boundary)s
      )
),
positive_edge AS (
    SELECT entity_a AS src, entity_b AS dst, decision_id
    FROM operative
    WHERE effect = 'same_identity'
    UNION ALL
    SELECT entity_b, entity_a, decision_id
    FROM operative
    WHERE effect = 'same_identity'
),
reach(src, dst) AS (
    SELECT src, dst FROM positive_edge
    UNION
    SELECT r.src, e.dst
    FROM reach r
    JOIN positive_edge e ON e.src = r.dst
),
conflict AS (
    SELECT d.decision_id, d.entity_a, d.entity_b
    FROM operative d
    WHERE d.effect = 'distinct'
      AND EXISTS (
          SELECT 1
          FROM reach r
          WHERE r.src = d.entity_a
            AND r.dst = d.entity_b
      )
)
"""

PROOF_B_BOUNDARY_QUERY = (
    _PROOF_B_CTES
    + """
SELECT 'operative' AS row_kind,
       decision_id,
       effect,
       entity_a,
       entity_b
FROM operative
UNION ALL
SELECT 'conflict', decision_id, 'CONFLICTED', entity_a, entity_b
FROM conflict
ORDER BY row_kind, decision_id
"""
)

#: Reconciliation section 3 pins exactly this projection shape.
PROOF_B_CLUSTER_QUERY = (
    _PROOF_B_CTES
    + """
SELECT DISTINCT src, dst
FROM reach
WHERE src < dst
ORDER BY src, dst
"""
)

# --------------------------------------------------------------------------
# Proof C -- typed forward/reverse provenance (harness section 4)
# --------------------------------------------------------------------------

#: Harness section 4.1, verbatim, plus the section 4.2 traversal view.
PROOF_C_SETUP = (
    "CREATE SCHEMA proof",
    "CREATE TABLE proof.decision (decision_id text PRIMARY KEY)",
    "CREATE TABLE proof.claim_version (claim_version_id text PRIMARY KEY)",
    "CREATE TABLE proof.observation (observation_id text PRIMARY KEY)",
    """
    CREATE TABLE proof.claim_version_observation_basis (
        claim_version_id text NOT NULL REFERENCES proof.claim_version,
        observation_id text NOT NULL REFERENCES proof.observation,
        relation_kind text NOT NULL CHECK (relation_kind IN ('supports', 'contradicts')),
        PRIMARY KEY (claim_version_id, observation_id, relation_kind)
    )
    """,
    """
    CREATE TABLE proof.claim_version_decision_dependency (
        claim_version_id text NOT NULL REFERENCES proof.claim_version,
        decision_id text NOT NULL REFERENCES proof.decision,
        dependency_kind text NOT NULL
            CHECK (dependency_kind IN ('identity_resolution', 'claim_posture')),
        PRIMARY KEY (claim_version_id, decision_id, dependency_kind)
    )
    """,
    """
    CREATE INDEX claim_version_observation_basis_reverse_idx
    ON proof.claim_version_observation_basis (observation_id, claim_version_id)
    """,
    """
    CREATE INDEX claim_version_decision_dependency_reverse_idx
    ON proof.claim_version_decision_dependency (decision_id, claim_version_id)
    """,
    "INSERT INTO proof.decision VALUES ('D2'), ('D20')",
    "INSERT INTO proof.claim_version VALUES ('C7V1')",
    "INSERT INTO proof.observation VALUES ('O4')",
    "INSERT INTO proof.claim_version_observation_basis VALUES ('C7V1', 'O4', 'supports')",
    """
    INSERT INTO proof.claim_version_decision_dependency VALUES
    ('C7V1', 'D2', 'identity_resolution'),
    ('C7V1', 'D20', 'claim_posture')
    """,
    """
    CREATE VIEW proof.provenance_edge_v AS
    SELECT
        'claim_version'::text AS dependent_type,
        claim_version_id AS dependent_id,
        relation_kind,
        'observation'::text AS source_type,
        observation_id AS source_id
    FROM proof.claim_version_observation_basis
    UNION ALL
    SELECT
        'claim_version',
        claim_version_id,
        dependency_kind,
        'decision',
        decision_id
    FROM proof.claim_version_decision_dependency
    """,
)

PROOF_C_FORWARD = """
SELECT source_type, source_id, relation_kind
FROM proof.provenance_edge_v
WHERE dependent_type = 'claim_version'
  AND dependent_id = %(dependent_id)s
ORDER BY source_type, source_id, relation_kind
"""

PROOF_C_REVERSE = """
SELECT dependent_type, dependent_id, relation_kind
FROM proof.provenance_edge_v
WHERE source_type = %(source_type)s
  AND source_id = %(source_id)s
ORDER BY dependent_type, dependent_id, relation_kind
"""

#: Harness section 4.3 adversaries plus the reconciliation section 4 addition.
#: Each runs inside its own recoverable savepoint and must be rejected.
PROOF_C_ADVERSARY_NONEXISTENT_FK = """
INSERT INTO proof.claim_version_decision_dependency
VALUES ('C7V1', 'NO_SUCH_DECISION', 'identity_resolution')
"""

PROOF_C_ADVERSARY_INVENTED_RELATION = """
INSERT INTO proof.claim_version_decision_dependency
VALUES ('C7V1', 'D2', 'whatever_model_invented')
"""

#: Reconciliation section 4: the UNION ALL view is intentionally a read-only
#: normalized traversal surface. Unexpected successful mutation is a proof
#: failure.
PROOF_C_ADVERSARY_VIEW_INSERT = """
INSERT INTO proof.provenance_edge_v
    (dependent_type, dependent_id, relation_kind, source_type, source_id)
VALUES ('claim_version', 'C7V1', 'supports', 'observation', 'O4')
"""
