# PostgreSQL Scratch Proof Harness 01

**Status:** NON-AUTHORITATIVE EXECUTION HARNESS

**Target:** PostgreSQL 18.x

**Depends on:** `POSTGRESQL-SCHEMA-SKETCH-01.md`

**Purpose:** Make the three migration-gating scratch proofs executable and falsifiable without creating the production Desk schema.

This document is not a migration or accepted schema. It defines disposable proof tables, session choreography, and pass/fail assertions. If observed PostgreSQL behavior contradicts the design sketch, revise the design rather than coding around the result.

---

# 1. Scratch database rules

Use a dedicated database such as:

```text
discrepancy_desk_foundation_proof_01
```

Rules:

1. no production Desk schema objects;
2. no real Evidence or credentials;
3. all proof objects live in schema `proof`;
4. record PostgreSQL version and relevant settings before testing;
5. destroy the scratch database only through an explicitly authorized cleanup path.

Preflight evidence:

```sql
SELECT version();
SHOW server_version;
SHOW track_commit_timestamp;
```

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

- PostgreSQL exact version;
- relevant settings;
- exact SQL executed;
- observed rows/results;
- whether any statement unexpectedly succeeded/failed;
- PASS/FAIL against the criteria above;
- design consequences for `FND-002`, `FND-008`, `FND-009`, `FND-010`, and `FND-011`.

Do not mark an open item resolved merely because the SQL parses. The proof must demonstrate the stated invariant under the adversarial case.
