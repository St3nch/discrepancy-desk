# PostgreSQL Scratch Proof Harness 01

**Status:** NON-AUTHORITATIVE EXECUTION HARNESS

**Target:** PostgreSQL 18.x

**Execution substrate:** disposable `postgres:18-alpine` container on a random loopback port

**Depends on:** `POSTGRESQL-SCHEMA-SKETCH-01.md`

**Purpose:** Make the three migration-gating scratch proofs executable and falsifiable without creating the production Desk schema.

This document is not a migration or accepted schema. It defines disposable proof tables, session choreography, and pass/fail assertions. If observed PostgreSQL behavior contradicts the design sketch, revise the design rather than coding around the result.

The substrate pattern intentionally follows the proven Observatory test fixture: start `postgres:18-alpine` with `--rm`, bind it only to a dynamically selected `127.0.0.1` port, wait for a real PostgreSQL connection, create isolated temporary databases, and tear everything down after the proof run. The Desk does not depend on a host-installed PostgreSQL cluster for these proofs.

---

# 1. Ephemeral PostgreSQL 18 substrate

## 1.1 Container lifecycle contract

Use exactly the PostgreSQL major targeted by the Desk:

```text
postgres:18-alpine
```

Rules:

1. choose a free host port dynamically and bind only `127.0.0.1:<random>:5432`;
2. start the container with a unique name and `--rm`;
3. use proof-only credentials and no real Desk Evidence, secrets, or production data;
4. attach no persistent volume;
5. wait for a real SQL connection before beginning a proof;
6. verify the **connected server**, not merely the image tag, is PostgreSQL major version 18;
7. create a unique temporary database for each proof so one proof cannot contaminate another;
8. force-drop each temporary database after its proof;
9. stop the container after the proof session, allowing `--rm` to remove it;
10. a failed teardown is visible test failure/cleanup debt, never permission to reuse unknown state.

The host PostgreSQL `18/main` cluster currently listening on port `5433` is **not part of this proof substrate**. Its presence or absence must not affect proof results.

## 1.2 Future automated fixture contract

When the Desk has an accepted implementation ticket and test package, the reusable fixture should mirror Observatory's proven behavior:

```text
session fixture
  ├─ find free 127.0.0.1 port
  ├─ docker run --rm postgres:18-alpine
  ├─ wait using a real psycopg connection
  ├─ SHOW server_version_num; require major == 18
  ├─ yield admin DSN
  └─ docker stop container

per-proof fixture
  ├─ CREATE DATABASE <unique-name>
  ├─ yield proof DSN
  └─ DROP DATABASE ... WITH (FORCE)
```

This document specifies that contract; it does **not** add Python/pytest infrastructure before the Writer implementation gate.

An explicit environment-selected external DSN may be supported later for CI or controlled diagnostics, but it must fail closed if unreachable or if `SHOW server_version_num` is not major 18. It must never silently fall back to another server after an explicit DSN was supplied.

## 1.3 Preflight evidence

For every proof database, capture:

```sql
SELECT version();
SHOW server_version_num;
SHOW server_version;
SHOW track_commit_timestamp;
```

The major-version assertion is numeric:

```text
integer(server_version_num) / 10000 == 18
```

Do not infer the exercised version from Docker metadata or presentation text alone.

## 1.4 Proof-database isolation

Run the three proofs in three different temporary databases inside the same disposable container session:

```text
proof A database  admission ordering / concurrency
proof B database  identity conflict / historical boundary
proof C database  typed provenance / integrity adversaries
```

All objects inside each database live under schema `proof`.

Proof A requires **two independent client connections to the same temporary proof-A database** so the advisory-lock behavior is real PostgreSQL concurrency rather than sequential statements in one session.

Proof B and Proof C must begin from newly created empty databases, not from Proof A's mutated state.

After each proof, force-drop its database. At the end of the session, stop the container. No proof database or container volume is retained as authoritative state.

---

# 2. Proof A — admission ordering under concurrency

## 2.1 Setup

```sql
CREATE SCHEMA proof;

CREATE SEQUENCE proof.record_admission_order_seq CACHE 1;

CREATE TABLE proof.record_admission (
    admission_order bigint PRIMARY KEY,
    label text NOT NULL,
    allocated_at timestamptz NOT NULL
);
```

Use one fixed advisory-lock key for this proof:

```text
90201001
```

## 2.2 Delayed-commit choreography

**Session A**

```sql
BEGIN;
SELECT pg_advisory_xact_lock(90201001);
INSERT INTO proof.record_admission
VALUES (
    nextval('proof.record_admission_order_seq'),
    'A-delayed-commit',
    clock_timestamp()
)
RETURNING *;
SELECT pg_sleep(8);
COMMIT;
```

Start Session B while A is sleeping.

**Session B**

```sql
BEGIN;
SELECT clock_timestamp() AS b_before_lock;
SELECT pg_advisory_xact_lock(90201001);
SELECT clock_timestamp() AS b_after_lock;
INSERT INTO proof.record_admission
VALUES (
    nextval('proof.record_admission_order_seq'),
    'B-waits-for-A',
    clock_timestamp()
)
RETURNING *;
COMMIT;
```

**PASS requires:**

- B blocks on the advisory lock until A ends;
- A receives a lower admission ordinal than B;
- B cannot allocate its ordinal while A still owns the transaction lock;
- committed ordinal order therefore follows the serialized governed admission gate.

## 2.3 Rollback-gap choreography

**Session C**

```sql
BEGIN;
SELECT pg_advisory_xact_lock(90201001);
INSERT INTO proof.record_admission
VALUES (
    nextval('proof.record_admission_order_seq'),
    'C-rolls-back',
    clock_timestamp()
)
RETURNING *;
ROLLBACK;
```

**Session D**

```sql
BEGIN;
SELECT pg_advisory_xact_lock(90201001);
INSERT INTO proof.record_admission
VALUES (
    nextval('proof.record_admission_order_seq'),
    'D-after-rollback',
    clock_timestamp()
)
RETURNING *;
COMMIT;
```

Verify:

```sql
TABLE proof.record_admission ORDER BY admission_order;
```

**PASS requires:** C's allocated value may be missing, D receives a later value, and the gap has no semantic meaning.

**FAIL if:** a later committed governed admission can obtain a lower ordinal than an earlier committed governed admission while all writers obey the lock-first rule.

---

# 3. Proof B — identity triangle, conflict, repair, historical boundary

## 3.1 Setup

```sql
CREATE TABLE proof.identity_decision (
    decision_id text PRIMARY KEY,
    admitted_order bigint NOT NULL,
    effect text NOT NULL CHECK (effect IN ('same_identity', 'distinct')),
    entity_a text NOT NULL,
    entity_b text NOT NULL,
    CHECK (entity_a < entity_b)
);

CREATE TABLE proof.identity_supersession (
    new_decision_id text NOT NULL REFERENCES proof.identity_decision(decision_id),
    superseded_decision_id text NOT NULL REFERENCES proof.identity_decision(decision_id),
    PRIMARY KEY (new_decision_id, superseded_decision_id)
);

INSERT INTO proof.identity_decision VALUES
('D1', 10, 'same_identity', 'E17', 'E42'),
('D2', 11, 'same_identity', 'E42', 'E99'),
('D3', 12, 'same_identity', 'E17', 'E99'),
('D8', 15, 'distinct',      'E17', 'E42'),
('D9', 20, 'distinct',      'E17', 'E42');

INSERT INTO proof.identity_supersession VALUES
('D9', 'D1'),
('D9', 'D3'),
('D9', 'D8');
```

## 3.2 Boundary query

For a chosen boundary `B`, compute the operative Decision set by excluding a Decision only when an admitted superseder exists at or before `B`.

In `psql`, set the boundary:

```sql
\set B 14
```

Then run:

```sql
WITH RECURSIVE
operative AS (
    SELECT d.*
    FROM proof.identity_decision d
    WHERE d.admitted_order <= :B
      AND NOT EXISTS (
          SELECT 1
          FROM proof.identity_supersession s
          JOIN proof.identity_decision newer
            ON newer.decision_id = s.new_decision_id
          WHERE s.superseded_decision_id = d.decision_id
            AND newer.admitted_order <= :B
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
SELECT 'operative' AS row_kind,
       decision_id,
       effect,
       entity_a,
       entity_b
FROM operative
UNION ALL
SELECT 'conflict', decision_id, 'CONFLICTED', entity_a, entity_b
FROM conflict
ORDER BY row_kind, decision_id;
```

To inspect the connected component relation itself, reuse the same `operative`, `positive_edge`, and `reach` CTEs and select distinct reachable pairs. The proof does not require inventing a canonical representative Entity; it requires proving connectivity and conflict behavior.

Run the same query at three boundaries:

```text
B = 14  expected: E17/E42/E99 one positive cluster, no conflict
B = 16  expected: CONFLICTED because D8 contradicts surviving positive paths
B = 21  expected: E17 separate; E42/E99 remain same via D2; no conflict
```

**PASS requires:**

- no arbitrary graph cut at B=16;
- D8 cannot silently override D1/D2/D3;
- explicit supersession at D9 repairs the graph;
- B=14 still reconstructs the pre-correction cluster after D9 exists.

**FAIL if:** current repair destroys the historical B=14 answer or if conflict is hidden by choosing an edge implicitly.

---

# 4. Proof C — typed forward/reverse provenance

## 4.1 Setup

```sql
CREATE TABLE proof.decision (
    decision_id text PRIMARY KEY
);

CREATE TABLE proof.claim_version (
    claim_version_id text PRIMARY KEY
);

CREATE TABLE proof.observation (
    observation_id text PRIMARY KEY
);

CREATE TABLE proof.claim_version_observation_basis (
    claim_version_id text NOT NULL REFERENCES proof.claim_version,
    observation_id text NOT NULL REFERENCES proof.observation,
    relation_kind text NOT NULL CHECK (relation_kind IN ('supports', 'contradicts')),
    PRIMARY KEY (claim_version_id, observation_id, relation_kind)
);

CREATE TABLE proof.claim_version_decision_dependency (
    claim_version_id text NOT NULL REFERENCES proof.claim_version,
    decision_id text NOT NULL REFERENCES proof.decision,
    dependency_kind text NOT NULL CHECK (dependency_kind IN ('identity_resolution', 'claim_posture')),
    PRIMARY KEY (claim_version_id, decision_id, dependency_kind)
);

CREATE INDEX claim_version_observation_basis_reverse_idx
ON proof.claim_version_observation_basis (observation_id, claim_version_id);

CREATE INDEX claim_version_decision_dependency_reverse_idx
ON proof.claim_version_decision_dependency (decision_id, claim_version_id);

INSERT INTO proof.decision VALUES ('D2'), ('D20');
INSERT INTO proof.claim_version VALUES ('C7V1');
INSERT INTO proof.observation VALUES ('O4');
INSERT INTO proof.claim_version_observation_basis VALUES ('C7V1', 'O4', 'supports');
INSERT INTO proof.claim_version_decision_dependency VALUES
('C7V1', 'D2', 'identity_resolution'),
('C7V1', 'D20', 'claim_posture');
```

## 4.2 Traversal proof

Create a read-only normalized traversal view:

```sql
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
FROM proof.claim_version_decision_dependency;
```

Forward:

```sql
SELECT source_type, source_id, relation_kind
FROM proof.provenance_edge_v
WHERE dependent_type = 'claim_version'
  AND dependent_id = 'C7V1'
ORDER BY source_type, source_id, relation_kind;
```

must answer:

```text
C7V1 → O4 supports
C7V1 → D2 identity_resolution
C7V1 → D20 claim_posture
```

Reverse:

```sql
SELECT dependent_type, dependent_id, relation_kind
FROM proof.provenance_edge_v
WHERE source_type = 'decision'
  AND source_id = 'D2';
```

must answer:

```text
D2 → C7V1
```

Repeat with `source_id = 'D20'` and with `source_type = 'observation', source_id = 'O4'` to prove the other reverse paths.

A read-only `UNION ALL` view may normalize those typed tables for traversal, but inserts remain impossible through any generic polymorphic edge API.

## 4.3 Integrity adversaries

Attempt each inside its own recoverable savepoint and require failure:

```sql
-- nonexistent FK target
SAVEPOINT bad_fk;
INSERT INTO proof.claim_version_decision_dependency
VALUES ('C7V1', 'NO_SUCH_DECISION', 'identity_resolution');
-- expected ERROR, then:
ROLLBACK TO SAVEPOINT bad_fk;
RELEASE SAVEPOINT bad_fk;

-- illegal relation vocabulary
SAVEPOINT bad_kind;
INSERT INTO proof.claim_version_decision_dependency
VALUES ('C7V1', 'D2', 'whatever_model_invented');
-- expected ERROR, then:
ROLLBACK TO SAVEPOINT bad_kind;
RELEASE SAVEPOINT bad_kind;
```

**PASS requires:** database FK/CHECK enforcement rejects both, while legitimate forward and reverse traversal remains simple and indexable.

---

# 5. Required execution report

For each proof record:

- container image reference used (`postgres:18-alpine`);
- unique container name and selected loopback host port;
- connected server `server_version_num` and proof that the numeric major is 18;
- temporary database name and teardown result;
- PostgreSQL exact version;
- relevant settings;
- exact SQL executed;
- observed rows/results;
- whether any statement unexpectedly succeeded/failed;
- PASS/FAIL against the criteria above;
- design consequences for `FND-002`, `FND-008`, `FND-009`, `FND-010`, and `FND-011`.

Do not mark an open item resolved merely because the SQL parses. The proof must demonstrate the stated invariant under the adversarial case.

The execution report must also state whether the host-installed PostgreSQL cluster was contacted. The expected answer for this harness is **no**.

---

# 6. Promotion boundary

Once these proofs pass, the successful SQL behavior may inform an accepted spec/ticket for the reusable Desk PostgreSQL test fixture. The fixture implementation itself belongs to the designated Writer and should copy the proven Observatory lifecycle semantics rather than introducing a second PostgreSQL testing convention.
